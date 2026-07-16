"""Create the cardiology expert panel (login + password), idempotently.

Each run ensures N expert accounts exist and (re)sets a fresh random password,
then prints a credential sheet to hand to the raters. Also writes the sheet to
``backend/expert_credentials.local.txt`` (local only -- do not commit/share the file).

    cd backend
    python scripts/seed_expert_panel.py --count 5
"""
import argparse
import asyncio
import os
import secrets
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import User
from app.security.passwords import hash_password

BACKEND_ROOT = Path(__file__).resolve().parents[1]
CRED_FILE = BACKEND_ROOT / "expert_credentials.local.txt"

EMAIL_DOMAIN = "cardio-panel.local"
# Avoid ambiguous characters (0/O, 1/l/I) in distributed passwords.
ALPHABET = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _password(length: int = 10) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


async def main() -> None:
    parser = argparse.ArgumentParser(description="Seed N cardiology expert accounts with fresh passwords.")
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--prefix", default="cardiologist")
    args = parser.parse_args()

    lines = ["email,password,full_name,role"]
    async with AsyncSessionLocal() as session:
        for i in range(1, args.count + 1):
            email = f"{args.prefix}{i}@{EMAIL_DOMAIN}".lower()
            full_name = f"Кардиолог-эксперт {i}"
            password = _password()
            result = await session.execute(select(User).where(User.email == email))
            user = result.scalars().first()
            if user:
                user.password_hash = hash_password(password)
                user.role = "expert"
                user.full_name = full_name
            else:
                session.add(
                    User(email=email, password_hash=hash_password(password), role="expert", full_name=full_name)
                )
            lines.append(f"{email},{password},{full_name},expert")
        await session.commit()

    sheet = "\n".join(lines) + "\n"
    CRED_FILE.write_text(sheet, encoding="utf-8")
    print(sheet)
    print(f"Credential sheet written to: {CRED_FILE}")
    print("NOTE: local file with plaintext passwords -- do not commit or email it as-is.")


if __name__ == "__main__":
    asyncio.run(main())
