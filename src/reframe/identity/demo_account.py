"""Opt-in, openly shared preview identity; never an administrator or a real mailbox.

These credentials are intentionally public and are returned to the login form.
They must not be reused for any other account or service.
"""
import uuid

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.reframe.identity.crypto import hash_password, verify_password
from src.reframe.identity.models import Profile, SpoilerPreferences, User, UserCredential


DEMO_USER_ID = uuid.uuid5(uuid.NAMESPACE_URL, "https://rescene.example/public-demo-viewer")
DEMO_EMAIL = "viewer@demo.rescene.example"
DEMO_PASSWORD = "ReScene-Demo-2026!"  # Intentionally public preview credential, not a secret.
DEMO_HANDLE = "rescene_demo_viewer"


async def ensure_demo_account(db: AsyncSession, *, _retry: bool = True) -> None:
    """Create only the reserved demo identity, or validate it without overwriting data."""
    result = await db.execute(select(User).where(or_(
        User.id == DEMO_USER_ID,
        User.email_normalized == DEMO_EMAIL,
        User.handle_normalized == DEMO_HANDLE,
    )))
    existing = result.scalars().all()
    if existing:
        if len(existing) != 1:
            raise RuntimeError("Demo account identity collision; existing accounts were not changed.")
        user = existing[0]
        credential = await db.get(UserCredential, DEMO_USER_ID)
        if (user.id != DEMO_USER_ID or user.email_normalized != DEMO_EMAIL
                or user.handle_normalized != DEMO_HANDLE or user.role != "USER"
                or user.status != "ACTIVE" or user.account_origin != "PUBLIC_DEMO"
                or credential is None
                or not verify_password(DEMO_PASSWORD, credential.password_hash)):
            raise RuntimeError("Reserved demo account does not match the preview configuration.")
        return

    try:
        db.add(User(id=DEMO_USER_ID, email_normalized=DEMO_EMAIL,
                    handle=DEMO_HANDLE, handle_normalized=DEMO_HANDLE,
                    status="ACTIVE", role="USER", account_origin="PUBLIC_DEMO", auth_version=1))
        await db.flush()
        db.add(Profile(user_id=DEMO_USER_ID, display_name="Demo Viewer", locale="en-US", fan_depth="REGULAR"))
        db.add(SpoilerPreferences(user_id=DEMO_USER_ID, default_mode="STRICT",
                                  mask_titles=True, mask_thumbnails=True, mask_comments=True))
        db.add(UserCredential(user_id=DEMO_USER_ID, password_hash=hash_password(DEMO_PASSWORD),
                              password_algorithm="argon2id", failed_attempt_count=0))
        await db.commit()
    except IntegrityError:
        await db.rollback()
        # Another application worker may have created the same reserved identity.
        # Re-check all invariants; never repurpose an existing account.
        if not _retry:
            raise
        await ensure_demo_account(db, _retry=False)


def public_demo_configuration(enabled: bool) -> dict:
    if not enabled:
        return {"enabled": False}
    return {"enabled": True, "email": DEMO_EMAIL, "password": DEMO_PASSWORD,
            "display_name": "Demo Viewer", "shared": True}
