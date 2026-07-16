"""
Создаёт демо-пользователей для входа (идемпотентно).

Только для локальной/dev-среды. Требует ALLOW_DEMO_SEED=true и паролей из
переменных окружения — без захардкоженных значений:

  cd backend
  ALLOW_DEMO_SEED=true \
  DEMO_TEACHER_PASSWORD=... DEMO_STUDENT_PASSWORD=... DEMO_EXPERT_PASSWORD=... \
  python scripts/seed_demo_users.py

Никогда не запускайте это в продакшене.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import User
from app.security.demo_credentials import demo_password, require_demo_seed_enabled
from app.security.passwords import hash_password

DEMO_USERS = [
    {"email": "teacher@demo.local", "role": "teacher", "full_name": "Демо Преподаватель"},
    {"email": "student@demo.local", "role": "student", "full_name": "Демо Студент"},
    {"email": "expert@demo.local", "role": "expert", "full_name": "Демо Эксперт"},
]


async def main() -> None:
    require_demo_seed_enabled("seed_demo_users")
    async with AsyncSessionLocal() as session:
        for spec in DEMO_USERS:
            email = spec["email"].lower().strip()
            password = demo_password(spec["role"])
            result = await session.execute(select(User).where(User.email == email))
            existing = result.scalars().first()
            if existing:
                existing.password_hash = hash_password(password)
                existing.role = spec["role"]
                existing.full_name = spec["full_name"]
                print(f"Updated: {email}")
            else:
                session.add(
                    User(
                        email=email,
                        password_hash=hash_password(password),
                        role=spec["role"],
                        full_name=spec["full_name"],
                    )
                )
                print(f"Created: {email}")
        await session.commit()
    print("Demo users ready.")


if __name__ == "__main__":
    asyncio.run(main())
