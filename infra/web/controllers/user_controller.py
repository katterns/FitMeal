from datetime import datetime

from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, EmailStr

from config.settings import get_settings
from infra.db.database import get_db
from infra.db.models import UserModel
from infra.web.security import create_access_token, get_current_user, hash_password, verify_password


auth_router = APIRouter(prefix="/auth", tags=["auth"])
user_router = APIRouter(prefix="/users", tags=["users"])


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    role: str
    balance: int
    created_at: datetime


@auth_router.post("/register", response_model=UserResponse)
def register(
    email: EmailStr = Body(...),
    password: str = Body(..., min_length=6),
    db=Depends(get_db),
):
    email_norm = email.lower().strip()
    existing = db.query(UserModel).filter(UserModel.email == email_norm).first()
    if existing:
        raise HTTPException(status_code=400, detail="Пользователь с таким email уже существует")

    admins = {p.strip().lower() for p in get_settings().admin_emails.split(",") if p.strip()}
    role = "admin" if email_norm in admins else "user"
    user = UserModel(email=email_norm, hashed_password=hash_password(password), balance=100, role=role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@auth_router.post("/login", response_model=TokenResponse)
def login(
    email: EmailStr = Body(...),
    password: str = Body(...),
    db=Depends(get_db),
):
    email_norm = email.lower().strip()
    user = db.query(UserModel).filter(UserModel.email == email_norm).first()
    if user is None or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный email или пароль")

    return TokenResponse(access_token=create_access_token(str(user.id)))


@user_router.get("/me", response_model=UserResponse)
def get_me(current_user=Depends(get_current_user)):
    return current_user
