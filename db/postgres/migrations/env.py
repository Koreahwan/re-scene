import asyncio
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context

from src.reframe.shared.config import settings
from src.reframe.shared.database import Base
# Import all models to register in metadata
import src.reframe.identity.models
import src.reframe.spoiler.models
import src.reframe.evidence.models
import src.reframe.jobs.models
import src.reframe.cost.models
import src.reframe.audit.models
import src.reframe.moderation.models
import src.reframe.community.models
import src.reframe.community.moderation_models
import src.reframe.proof.models
import src.reframe.simulation.models
import src.reframe.catalog.models
import src.reframe.catalog.views

try:
    config = context.config
    if config and config.config_file_name is not None:
        fileConfig(config.config_file_name)
except AttributeError:
    config = None

target_metadata = Base.metadata



import sqlalchemy as sa

def ensure_version_table_width(connection: Connection) -> None:
    """Guarantees alembic_version.version_num is VARCHAR(128) before long revision IDs are inserted."""
    dialect_name = connection.dialect.name
    if dialect_name == "postgresql":
        connection.execute(sa.text("""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_name = 'alembic_version'
                ) THEN
                    ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(128);
                ELSE
                    CREATE TABLE alembic_version (
                        version_num VARCHAR(128) NOT NULL,
                        CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
                    );
                END IF;
            END $$;
        """))
    elif dialect_name == "sqlite":
        connection.execute(sa.text("""
            CREATE TABLE IF NOT EXISTS alembic_version (
                version_num VARCHAR(128) NOT NULL PRIMARY KEY
            );
        """))


def validate_migration_target_url(target_url: str) -> None:
    if not target_url:
        return
    clean = target_url.lower().replace("\\", "/")
    if "reframe_v7.db" in clean:
        raise ValueError(
            f"ISOLATION_VIOLATION: Alembic migrations cannot be executed against pristine original database "
            f"'{target_url}'. All Phase 1 migrations must target an isolated DB (e.g. ./data/phase1_submission.db)."
        )


def run_migrations_offline() -> None:
    main_url = config.get_main_option("sqlalchemy.url") if config else None
    url = main_url or settings.SYNC_DATABASE_URL
    validate_migration_target_url(url)
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table_col_args={"type_": sa.String(128)}
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    ensure_version_table_width(connection)
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table_col_args={"type_": sa.String(128)}
    )
    with context.begin_transaction():
        context.run_migrations()



async def run_async_migrations() -> None:
    configuration = config.get_section(config.config_ini_section) or {} if config else {}
    x_args = context.get_x_argument(as_dictionary=True) if context else {}
    x_url = x_args.get("url")
    main_url = x_url or (config.get_main_option("sqlalchemy.url") if config else None)
    if main_url:
        if main_url.startswith("sqlite:///") and not main_url.startswith("sqlite+aiosqlite:///"):
            main_url = main_url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
        configuration["sqlalchemy.url"] = main_url
    elif "sqlalchemy.url" not in configuration:
        configuration["sqlalchemy.url"] = settings.DATABASE_URL

    validate_migration_target_url(configuration.get("sqlalchemy.url"))

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
        await connection.commit()
    await connectable.dispose()



def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if config is not None:
    if context.is_offline_mode():
        run_migrations_offline()
    else:
        run_migrations_online()

