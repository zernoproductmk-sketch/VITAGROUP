from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from .auth import (
    CurrentUser,
    authenticate,
    change_password,
    create_access_token,
)
from .config import settings

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


class LoginInput(BaseModel):
    email: EmailStr
    password: str


class PasswordChangeInput(BaseModel):
    current_password: str
    new_password: str = Field(min_length=12, max_length=200)


@router.post("/login")
def login(payload: LoginInput, request: Request):
    forwarded_for = request.headers.get("x-forwarded-for")
    ip_address = (
        forwarded_for.split(",")[0].strip()
        if forwarded_for
        else (request.client.host if request.client else None)
    )
    user = authenticate(
        payload.email,
        payload.password,
        ip_address=ip_address,
        user_agent=request.headers.get("user-agent"),
    )
    token = create_access_token(
        UUID(user["id"]),
        user["roles"],
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": settings.auth_access_token_minutes * 60,
        "user": user,
    }


@router.get("/me")
def me(user: CurrentUser):
    return user


@router.post("/change-password")
def password_change(
    payload: PasswordChangeInput,
    user: CurrentUser,
):
    try:
        change_password(
            UUID(user["id"]),
            payload.current_password,
            payload.new_password,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok"}
