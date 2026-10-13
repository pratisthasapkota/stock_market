"""Keeps the seeded demo logins in step with the DEMO_* settings.

Lives here rather than in scripts/seed_demo.py so the app can reconcile the
accounts on every boot, not only on an empty database. Creating only-missing
users is not enough: the DEMO_* env vars (and the passwords the login page
fetches from /api/auth/demo-accounts) can change after the first seed, and a
stale hash would then 401 every demo login.
"""
from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from ..security import hash_password, verify_password


def seed_demo_users(db: Session) -> int:
    """Create or update the demo accounts so they match the current settings.

    No-op while DEMO_MODE is off. Returns how many accounts were created or
    changed, so callers can decide whether the session is worth committing.
    """
    if not settings.demo_mode:
        return 0

    changed = 0
    for acct in settings.demo_accounts:
        user = db.query(models.User).filter_by(username=acct["username"]).first()
        if user is None:
            db.add(
                models.User(
                    email=acct["email"],
                    username=acct["username"],
                    role=acct["role"],
                    password_hash=hash_password(acct["password"]),
                )
            )
            changed += 1
            continue
        # only rewrite the row when something actually drifted, so an unchanged
        # config does not churn the password hash (and its salt) every boot
        if (
            user.email != acct["email"]
            or user.role != acct["role"]
            or not user.is_active
            or not verify_password(acct["password"], user.password_hash)
        ):
            user.email = acct["email"]
            user.role = acct["role"]
            user.password_hash = hash_password(acct["password"])
            user.is_active = True
            changed += 1

    db.flush()
    return changed
