from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ReferenceGraph


class ReferenceGraphRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, graph_id: int) -> Optional[ReferenceGraph]:
        result = await self._session.execute(
            select(ReferenceGraph).where(ReferenceGraph.id == graph_id)
        )
        return result.scalars().first()
