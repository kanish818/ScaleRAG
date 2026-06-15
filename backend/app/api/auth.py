"""Auth router — email/password + Google OAuth 2.0."""
import logging
import os
from datetime import timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, get_current_user, hash_password, verify_password
from app.models.user import User
from app.services.rate_limiter import rate_limiter

logger = logging.getLogger(__name__)
router = APIRouter()


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    email: str
    name: str
    created_at: str
    model_config = {"from_attributes": True}


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


def _make_token(user: User) -> str:
    return create_access_token({"sub": str(user.id)}, timedelta(minutes=settings.JWT_EXPIRE_MINUTES))


def _user_out(user: User) -> UserOut:
    return UserOut(id=user.id, email=user.email, name=user.name,
                   created_at=user.created_at.isoformat() if user.created_at else "")


def _google_redirect_uri() -> str:
    if settings.GOOGLE_REDIRECT_URI:
        return settings.GOOGLE_REDIRECT_URI
    render_url = os.getenv("RENDER_EXTERNAL_URL", "").strip()
    if render_url:
        return f"{render_url.rstrip('/')}/api/auth/google/callback"
    return "http://localhost:8000/api/auth/google/callback"


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    rate_limiter.enforce(f"auth:register:{request.client.host}", settings.AUTH_RATE_LIMIT_RPM)
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Email already registered.")
    user = User(email=payload.email, hashed_password=hash_password(payload.password), name=payload.name)
    db.add(user)
    db.commit()
    db.refresh(user)
    return AuthResponse(access_token=_make_token(user), user=_user_out(user))


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    rate_limiter.enforce(f"auth:login:{request.client.host}", settings.AUTH_RATE_LIMIT_RPM)
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not user.hashed_password or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password.")
    return AuthResponse(access_token=_make_token(user), user=_user_out(user))


@router.get("/google")
def google_login(request: Request):
    rate_limiter.enforce(f"auth:google:{request.client.host}", settings.AUTH_RATE_LIMIT_RPM)
    params = "&".join([
        f"client_id={settings.GOOGLE_CLIENT_ID}",
        f"redirect_uri={_google_redirect_uri()}",
        "response_type=code",
        "scope=openid email profile",
        "access_type=offline",
        "prompt=select_account",
    ])
    return RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{params}")


@router.get("/google/callback")
def google_callback(code: str, request: Request, db: Session = Depends(get_db)):
    rate_limiter.enforce(f"auth:google-callback:{request.client.host}", settings.AUTH_RATE_LIMIT_RPM)
    try:
        with httpx.Client() as c:
            token_r = c.post("https://oauth2.googleapis.com/token", data={
                "code": code, "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": _google_redirect_uri(), "grant_type": "authorization_code",
            }, timeout=15)
            token_r.raise_for_status()
            access_token = token_r.json().get("access_token")
            userinfo = c.get("https://www.googleapis.com/oauth2/v2/userinfo",
                             headers={"Authorization": f"Bearer {access_token}"}, timeout=15).json()
    except Exception as exc:
        logger.error("Google OAuth error: %s", exc)
        return RedirectResponse(f"{settings.FRONTEND_URL}/?error=oauth_failed")

    google_id = userinfo.get("id")
    email = userinfo.get("email")
    name = userinfo.get("name") or email
    if not google_id or not email:
        return RedirectResponse(f"{settings.FRONTEND_URL}/?error=missing_user_info")

    user = db.query(User).filter(User.google_id == google_id).first()
    if not user:
        user = db.query(User).filter(User.email == email).first()
        if user:
            user.google_id = google_id
        else:
            user = User(email=email, name=name, google_id=google_id)
            db.add(user)
    db.commit()
    db.refresh(user)
    return RedirectResponse(f"{settings.FRONTEND_URL}/?token={_make_token(user)}")


@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)):
    return _user_out(current_user)
