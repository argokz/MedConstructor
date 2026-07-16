from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: int) -> Optional[User]:
        res = await self._session.execute(select(User).where(User.id == user_id))
        return res.scalars().first()

    async def get_by_email(self, email: str) -> Optional[User]:
        res = await self._session.execute(select(User).where(User.email == email.lower().strip()))
        return res.scalars().first()

    def add(self, user: User) -> None:
        self._session.add(user)
