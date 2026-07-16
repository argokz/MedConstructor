from sqlalchemy.ext.asyncio import AsyncSession

from app.models import StudentAttempt


class StudentAttemptRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, attempt: StudentAttempt) -> StudentAttempt:
        self._session.add(attempt)
        return attempt
