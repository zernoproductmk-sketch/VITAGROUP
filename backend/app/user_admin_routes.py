from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field

from .auth import require_roles
from .user_admin import (
    create_user,
    list_users,
    set_user_active,
    set_user_roles,
)

router = APIRouter(
    prefix="/api/v1/admin/users",
    tags=["User administration"],
    dependencies=[Depends(require_roles("ADMIN"))],
)


class UserCreateInput(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=200)
    roles: list[str]
    employee_id: UUID | None = None


class RolesInput(BaseModel):
    roles: list[str]


class ActiveInput(BaseModel):
    is_active: bool


@router.get("")
def users():
    return {"rows": list_users()}


@router.post("")
def user_create(payload: UserCreateInput):
    try:
        return create_user(
            payload.email,
            payload.password,
            payload.roles,
            payload.employee_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/{user_id}/roles")
def roles(user_id: UUID, payload: RolesInput):
    try:
        return set_user_roles(user_id, payload.roles)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/{user_id}/active")
def active(user_id: UUID, payload: ActiveInput):
    try:
        return set_user_active(user_id, payload.is_active)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
