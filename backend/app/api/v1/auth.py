from datetime import timedelta

from fastapi import APIRouter, HTTPException, status
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DbSession, SettingsDep
from app.models import User
from app.repositories.user import UserRepository
from app.schemas import TokenResponse, UserLoginRequest, UserPublic, UserRegisterRequest
from app.security.jwt_tokens import create_access_token
from app.security.passwords import hash_password, verify_password

router = APIRouter(tags=["auth"])


@router.post("/auth/register", response_model=UserPublic)
async def register(body: UserRegisterRequest, db: DbSession) -> UserPublic:
    repo = UserRepository(db)
    if await repo.get_by_email(body.email):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    user = User(
        email=body.email.lower().strip(),
        password_hash=hash_password(body.password),
        full_name=body.full_name,
        role="student",
    )
    repo.add(user)
    try:
        await db.commit()
        await db.refresh(user)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    return UserPublic(
        id=user.id,
        email=user.email,
        role=user.role,
        full_name=user.full_name,
        specialty_id=user.specialty_id,
        group_id=user.group_id,
    )


@router.post("/auth/login", response_model=TokenResponse)
async def login(body: UserLoginRequest, db: DbSession, settings: SettingsDep) -> TokenResponse:
    repo = UserRepository(db)
    user = await repo.get_by_email(body.email)
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_access_token(
        {"sub": str(user.id), "role": user.role},
        settings.jwt_secret_key,
        settings.jwt_algorithm,
        timedelta(minutes=settings.access_token_expire_minutes),
    )
    return TokenResponse(access_token=token)


@router.get("/auth/me", response_model=UserPublic)
async def me(user: CurrentUser) -> UserPublic:
    return UserPublic(
        id=user.id,
        email=user.email,
        role=user.role,
        full_name=user.full_name,
        specialty_id=user.specialty_id,
        group_id=user.group_id,
    )
