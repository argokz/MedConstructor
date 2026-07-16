"""Centralised, safe handling of demo-account credentials.

Demo accounts (``*@demo.local``) must never be created with hardcoded, publicly
known passwords, because the source is public. This module is the single place
that decides whether demo seeding is allowed and where demo passwords come from.

Rules:
- Demo seeding via the explicit scripts requires ``ALLOW_DEMO_SEED=true``.
- Passwords come only from ``DEMO_<ROLE>_PASSWORD`` environment variables.
- There is no insecure default. When a password is not provided, callers either
  refuse (explicit seed scripts) or fall back to a strong random password that
  nobody knows (the runtime demo importer, where the account only needs to own
  demo data, not to be an interactive login).
"""
from __future__ import annotations

import os
import secrets

DEMO_SEED_FLAG = "ALLOW_DEMO_SEED"


def demo_seed_allowed() -> bool:
    """True only when ``ALLOW_DEMO_SEED`` is explicitly set to ``true``."""
    return os.environ.get(DEMO_SEED_FLAG, "").strip().lower() == "true"


def require_demo_seed_enabled(context: str) -> None:
    """Refuse to create demo accounts unless demo seeding is explicitly enabled."""
    if not demo_seed_allowed():
        raise RuntimeError(
            f"{context}: refusing to create demo accounts because {DEMO_SEED_FLAG} "
            f"is not 'true'. Enable it only in a local/development environment and "
            f"provide DEMO_*_PASSWORD environment variables. Never enable this in "
            f"production."
        )


def demo_password(role_key: str, *, generate_if_missing: bool = False) -> str:
    """Return the password for a demo account role.

    ``role_key`` is a role name such as ``teacher``/``student``/``expert``; the
    matching environment variable is ``DEMO_<ROLE>_PASSWORD``.

    - If the variable is set, its value is used.
    - If it is not set and ``generate_if_missing`` is True, a strong random
      password is generated (the account will exist but have no known login).
    - Otherwise a ``RuntimeError`` is raised — there is no hardcoded default.
    """
    env_name = f"DEMO_{role_key.strip().upper()}_PASSWORD"
    value = os.environ.get(env_name)
    if value:
        return value
    if generate_if_missing:
        return secrets.token_urlsafe(24)
    raise RuntimeError(
        f"{env_name} is not set. Refusing to fall back to a hardcoded password. "
        f"Set {env_name} in your local environment to seed this demo account."
    )
