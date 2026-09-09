#!/usr/bin/env python3
"""
Reframe V7 Local Admin & Moderator Role Promotion CLI
Promotes a verified existing user account to ADMIN or MODERATOR role for local testing and demonstration.
Never logs passwords, tokens, tickets, or secrets. Unconditionally refuses production execution.
"""
from __future__ import annotations
import argparse
import asyncio
import sys
import re
from pathlib import Path

# Add project root and src to path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "src"))

from sqlalchemy import select
from src.reframe.shared.config import settings
from src.reframe.shared.database import AsyncSessionLocal
from src.reframe.identity.models import User


EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


async def promote_user(email: str, target_role: str = "ADMIN", confirm_yes: bool = False) -> bool:
    email_norm = email.strip().lower()
    target_role = target_role.strip().upper()

    # 1. Unconditionally reject production environment
    if settings.ENVIRONMENT == "production":
        print("[BLOCKED] Promotion strictly prohibited in production environment. No bypass exists.")
        return False

    # 2. Validate email format
    if not EMAIL_REGEX.match(email_norm):
        print(f"[ERROR] Invalid email format: '{email_norm}'")
        return False

    # 3. Validate role
    if target_role not in ("ADMIN", "MODERATOR", "USER"):
        print(f"[ERROR] Invalid role '{target_role}'. Allowed roles: ADMIN, MODERATOR, USER")
        return False

    if not confirm_yes:
        resp = input(f"Are you sure you want to change role of '{email_norm}' to {target_role}? [y/N]: ").strip().lower()
        if resp not in ("y", "yes"):
            print("[ABORTED] Operation cancelled by user.")
            return False

    async with AsyncSessionLocal() as db:
        stmt = select(User).where(User.email_normalized == email_norm)
        res = await db.execute(stmt)
        user = res.scalar_one_or_none()

        if not user:
            print(f"[ERROR] User with email '{email_norm}' not found.")
            return False

        old_role = user.role
        user.role = target_role
        user.auth_version = getattr(user, "auth_version", 1) + 1  # Invalidate old sessions
        await db.commit()

        print(f"[SUCCESS] User '{email_norm}' role updated: {old_role} -> {target_role} (auth_version incremented to {user.auth_version})")
        return True


def main():
    parser = argparse.ArgumentParser(description="Promote a Reframe user account to ADMIN or MODERATOR (Non-production only).")
    parser.add_argument("email", help="Email address of the existing user account to promote")
    parser.add_argument("--role", choices=["ADMIN", "MODERATOR", "USER"], default="ADMIN", help="Target role (default: ADMIN)")
    parser.add_argument("-y", "--yes", action="store_true", help="Skip interactive confirmation prompt")
    args = parser.parse_args()

    success = asyncio.run(promote_user(args.email, args.role, args.yes))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
