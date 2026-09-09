"""Ranking counters against isolated test storage; no production writes."""
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
from unittest.mock import AsyncMock

from httpx import AsyncClient, ASGITransport
from sqlalchemy import select, func

from apps.api.main import app
from src.reframe.catalog.views import ContentView, view_counts
from src.reframe.shared.database import AsyncSessionLocal
from src.reframe.shared.redis_client import redis_client
from src.reframe.community.models import Post, PostVersion
from src.reframe.identity.models import PUBLIC_AUTHOR_USER_ID


async def test_rolling_seven_days_excludes_old_and_future_views():
    now = datetime.now(timezone.utc)
    content_id = str(uuid4())
    async with AsyncSessionLocal() as db:
        for delta in [timedelta(days=-8), timedelta(days=-7), timedelta(days=-6), timedelta(seconds=1)]:
            db.add(ContentView(kind="film", content_id=content_id, event_id=uuid4(), viewed_at=now + delta))
        await db.commit()
        assert await view_counts(db, "film", [content_id], now) == {content_id: {"view_count": 3, "views_7d": 2}}
        assert await view_counts(db, "article", [content_id], now) == {}


async def test_film_views_deduplicate_and_reject_invalid_cross_site_and_rate_limited(monkeypatch):
    monkeypatch.setattr(redis_client, "incr", AsyncMock(return_value=1))
    event = str(uuid4())
    url = "/api/v1/films/the-bat-whispers-1930/views"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for _ in range(2):
            response = await client.post(url, json={"event_id": event})
            assert response.status_code == 200, response.text
        invalid = await client.post("/api/v1/films/no-such-film/views", json={"event_id": event})
        assert invalid.status_code == 404, invalid.text
        assert (await client.post(url, json={"event_id": "not-a-uuid"})).status_code == 422
        assert (await client.post(url, json={"event_id": str(uuid4())}, headers={"Sec-Fetch-Site": "cross-site"})).status_code == 403
        monkeypatch.setattr(redis_client, "incr", AsyncMock(return_value=121))
        assert (await client.post(url, json={"event_id": str(uuid4())})).status_code == 429
    async with AsyncSessionLocal() as db:
        assert await db.scalar(select(func.count()).select_from(ContentView).where(ContentView.event_id == UUID(event))) == 1


async def test_only_readable_published_articles_count_and_list_exposes_metrics(monkeypatch):
    monkeypatch.setattr(redis_client, "incr", AsyncMock(return_value=1))
    article_id, draft_id = uuid4(), uuid4()
    async with AsyncSessionLocal() as db:
        for post_id, status in [(article_id, "PUBLISHED"), (draft_id, "DRAFT")]:
            version_id = uuid4()
            db.add(Post(id=post_id, author_id=PUBLIC_AUTHOR_USER_ID, work_id="the-bat-whispers-1930",
                edition_id="tbw-fullscreen-archive", content_type="MAGAZINE_ARTICLE", status=status,
                published_at=datetime.now(timezone.utc) if status == "PUBLISHED" else None))
            await db.flush()
            db.add(PostVersion(id=version_id, post_id=post_id, version_no=1, title="View-count test",
                body_markdown='{"paragraphs":["A readable editorial."]}', body_sanitized_html="<p>A readable editorial.</p>",
                created_by=PUBLIC_AUTHOR_USER_ID))
        await db.commit()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        event = {"event_id": str(uuid4())}
        for _ in range(2):
            response = await client.post(f"/api/v1/magazine/{article_id}/views", json=event)
            assert response.status_code == 200, response.text
        assert (await client.post(f"/api/v1/magazine/{draft_id}/views", json=event)).status_code == 404
        assert (await client.post(f"/api/v1/magazine/{uuid4()}/views", json=event)).status_code == 404
        response = await client.get("/api/v1/magazine")
        assert response.status_code == 200, response.text
        article = next(item for item in response.json()["articles"] if item["article_id"] == str(article_id))
        assert article["view_count"] == article["views_7d"] == 1
        assert article["registered_at"] == article["published_at"]


async def test_limiter_failure_does_not_record_a_view(monkeypatch):
    monkeypatch.setattr(redis_client, "incr", AsyncMock(side_effect=RuntimeError("unavailable")))
    event = uuid4()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post('/api/v1/films/the-bat-whispers-1930/views', json={"event_id": str(event)})
        assert response.status_code == 503
        assert (await client.get('/api/v1/films/the-bat-whispers-1930')).status_code == 200
    async with AsyncSessionLocal() as db:
        assert await db.scalar(select(func.count()).select_from(ContentView).where(ContentView.event_id == event)) == 0


def test_additive_view_migration_preserves_existing_data(monkeypatch):
    import importlib.util
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import create_engine, inspect, text
    path = Path(__file__).resolve().parents[2] / 'db/postgres/migrations/versions/0021_content_views.py'
    spec = importlib.util.spec_from_file_location('view_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with create_engine('sqlite:///:memory:').begin() as connection:
        connection.execute(text('CREATE TABLE preserved (value TEXT)'))
        connection.execute(text("INSERT INTO preserved VALUES ('keep')"))
        monkeypatch.setattr(migration, 'op', Operations(MigrationContext.configure(connection)))
        migration.upgrade()
        assert 'content_views' in inspect(connection).get_table_names()
        assert len(inspect(connection).get_pk_constraint('content_views')['constrained_columns']) == 3
        assert connection.scalar(text('SELECT value FROM preserved')) == 'keep'
        migration.downgrade()
        assert 'content_views' not in inspect(connection).get_table_names()
        assert connection.scalar(text('SELECT value FROM preserved')) == 'keep'
