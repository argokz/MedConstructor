from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Assignment


class AssignmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_active(self) -> List[Assignment]:
        res = await self._session.execute(
            select(Assignment).order_by(Assignment.id.asc())
        )
        return list(res.scalars().all())
