"""Create/update the demo teacher account (local/dev only).

Requires ALLOW_DEMO_SEED=true and DEMO_TEACHER_PASSWORD in the environment.
Never run this in production.
"""
import asyncio

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import User
from app.security.demo_credentials import demo_password, require_demo_seed_enabled
from app.security.passwords import hash_password


async def create_demo_teacher():
    require_demo_seed_enabled("create_demo_teacher")
    password = demo_password("teacher")
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).filter_by(email="teacher@demo.local"))
        user = result.scalar_one_or_none()
        if not user:
            user = User(
                email="teacher@demo.local",
                password_hash=hash_password(password),
                full_name="Demo Teacher",
                role="teacher"
            )
            session.add(user)
            await session.commit()
            print("User created!")
        else:
            user.password_hash = hash_password(password)
            user.role = "teacher"
            await session.commit()
            print("User updated!")

if __name__ == "__main__":
    asyncio.run(create_demo_teacher())
