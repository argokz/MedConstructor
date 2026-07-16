from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DbSession
from app.models import Specialty, StudentGroup, User
from app.schemas import (
    SpecialtyCreate,
    SpecialtyListResponse,
    SpecialtyPublic,
    StudentGroupCreate,
    StudentGroupListResponse,
    StudentGroupPublic,
    UserCreateRequest,
    UserListResponse,
    UserPublic,
    UserUpdateRequest,
)
from app.security.passwords import hash_password

router = APIRouter(prefix="/admin", tags=["admin"])


def require_admin(user: CurrentUser) -> User:
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can manage users and curriculum structure.",
        )
    return user


def user_public(user: User) -> UserPublic:
    return UserPublic(
        id=user.id,
        email=user.email,
        role=user.role,
        full_name=user.full_name,
        specialty_id=user.specialty_id,
        group_id=user.group_id,
    )


@router.get("/users", response_model=UserListResponse)
async def list_users(db: DbSession, current_user: CurrentUser) -> UserListResponse:
    require_admin(current_user)
    rows = await db.execute(select(User).order_by(User.role.asc(), User.email.asc()))
    return UserListResponse(items=[user_public(user) for user in rows.scalars().all()])


@router.post("/users", response_model=UserPublic)
async def create_user(
    body: UserCreateRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> UserPublic:
    require_admin(current_user)
    user = User(
        email=body.email.lower().strip(),
        password_hash=hash_password(body.password),
        full_name=body.full_name,
        role=body.role,
        specialty_id=body.specialty_id,
        group_id=body.group_id,
    )
    db.add(user)
    try:
        await db.commit()
        await db.refresh(user)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    return user_public(user)


@router.patch("/users/{user_id}", response_model=UserPublic)
async def update_user(
    user_id: int,
    body: UserUpdateRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> UserPublic:
    require_admin(current_user)
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if body.email is not None:
        user.email = body.email.lower().strip()
    if body.password:
        user.password_hash = hash_password(body.password)
    if body.full_name is not None:
        user.full_name = body.full_name
    if body.role is not None:
        user.role = body.role
    if body.specialty_id is not None:
        user.specialty_id = body.specialty_id
    if body.group_id is not None:
        user.group_id = body.group_id

    try:
        await db.commit()
        await db.refresh(user)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User update conflicts with existing data")
    return user_public(user)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, db: DbSession, current_user: CurrentUser) -> None:
    require_admin(current_user)
    if user_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Administrator cannot delete own account")
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    await db.delete(user)
    await db.commit()


@router.get("/specialties", response_model=SpecialtyListResponse)
async def list_specialties(db: DbSession, current_user: CurrentUser) -> SpecialtyListResponse:
    require_admin(current_user)
    rows = await db.execute(select(Specialty).order_by(Specialty.name.asc()))
    return SpecialtyListResponse(
        items=[
            SpecialtyPublic(id=row.id, name=row.name, code=row.code, description=row.description)
            for row in rows.scalars().all()
        ]
    )


@router.post("/specialties", response_model=SpecialtyPublic)
async def create_specialty(
    body: SpecialtyCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> SpecialtyPublic:
    require_admin(current_user)
    row = Specialty(name=body.name.strip(), code=body.code.strip() if body.code else None, description=body.description)
    db.add(row)
    try:
        await db.commit()
        await db.refresh(row)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Specialty already exists")
    return SpecialtyPublic(id=row.id, name=row.name, code=row.code, description=row.description)


@router.delete("/specialties/{specialty_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_specialty(specialty_id: int, db: DbSession, current_user: CurrentUser) -> None:
    require_admin(current_user)
    row = await db.get(Specialty, specialty_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Specialty not found")
    await db.delete(row)
    await db.commit()


@router.get("/groups", response_model=StudentGroupListResponse)
async def list_groups(db: DbSession, current_user: CurrentUser) -> StudentGroupListResponse:
    require_admin(current_user)
    rows = await db.execute(select(StudentGroup).order_by(StudentGroup.name.asc()))
    return StudentGroupListResponse(
        items=[
            StudentGroupPublic(id=row.id, name=row.name, specialty_id=row.specialty_id, year=row.year)
            for row in rows.scalars().all()
        ]
    )


@router.post("/groups", response_model=StudentGroupPublic)
async def create_group(
    body: StudentGroupCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> StudentGroupPublic:
    require_admin(current_user)
    row = StudentGroup(name=body.name.strip(), specialty_id=body.specialty_id, year=body.year)
    db.add(row)
    try:
        await db.commit()
        await db.refresh(row)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Group already exists")
    return StudentGroupPublic(id=row.id, name=row.name, specialty_id=row.specialty_id, year=row.year)


@router.delete("/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(group_id: int, db: DbSession, current_user: CurrentUser) -> None:
    require_admin(current_user)
    row = await db.get(StudentGroup, group_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    await db.delete(row)
    await db.commit()
