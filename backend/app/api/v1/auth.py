from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import (
    clear_session_cookie,
    client_ip,
    dummy_verify,
    lock_until,
    make_session_token,
    new_csrf,
    read_session_token,
    require_csrf,
    set_session_cookie,
    utcnow,
    verify_password,
)
from app.infrastructure.db.models import LoginAttempt, User
from app.infrastructure.db.session import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginBody(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)


def current_session(request: Request) -> dict | None:
    raw = request.cookies.get("velar_session")
    if not raw:
        return None
    return read_session_token(raw)


def require_admin(request: Request, db: Session = Depends(get_db)) -> User:
    session = current_session(request)
    if not session or session.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No autenticado")
    require_csrf(request, session)
    user = db.get(User, session.get("uid"))
    if not user or user.role != "admin":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No autenticado")
    return user


def require_user(request: Request, db: Session = Depends(get_db)) -> User:
    session = current_session(request)
    if not session:
        raise HTTPException(status_code=401, detail="Inicia sesión para registrar selecciones")
    require_csrf(request, session)
    user = db.get(User, session.get("uid"))
    if not user or user.role != session.get("role"):
        raise HTTPException(status_code=401, detail="Sesión inválida")
    return user


@router.get("/csrf")
def csrf(request: Request, response: Response):
    session = current_session(request)
    token = (session or {}).get("csrf") or new_csrf()
    if session:
        session["csrf"] = token
        set_session_cookie(response, make_session_token(session))
    response.set_cookie(
        key="velar_csrf",
        value=token,
        httponly=False,
        samesite="lax",
        secure=get_settings().app_env == "production",
        max_age=get_settings().session_hours * 3600,
        path="/",
    )
    return {"csrf": token}


@router.get("/me")
def me(request: Request, db: Session = Depends(get_db)):
    session = current_session(request)
    if not session:
        return {"authenticated": False}
    user = db.get(User, session.get("uid"))
    if not user:
        return {"authenticated": False}
    return {"authenticated": True, "username": user.username, "role": user.role, "csrf": session.get("csrf")}


@router.post("/login")
def login(body: LoginBody, request: Request, response: Response, db: Session = Depends(get_db)):
    cookie_csrf = request.cookies.get("velar_csrf") or ""
    header_csrf = request.headers.get("x-csrf-token") or ""
    if not cookie_csrf or not header_csrf or not secrets.compare_digest(cookie_csrf, header_csrf):
        raise HTTPException(status_code=403, detail="CSRF inválido")
    settings = get_settings()
    ip = client_ip(request)
    username = body.username.strip().lower()
    now = utcnow()
    from datetime import timedelta

    window = now - timedelta(minutes=settings.login_lock_minutes)
    ip_fails = (
        db.query(func.count(LoginAttempt.id))
        .filter(LoginAttempt.ip == ip, LoginAttempt.success.is_(False), LoginAttempt.created_at > window)
        .scalar()
        or 0
    )
    if ip_fails >= settings.login_max_attempts * 3:
        raise HTTPException(status_code=429, detail="Demasiados intentos. Espera unos minutos.")

    user = db.query(User).filter(func.lower(User.username) == username).one_or_none()
    if user and user.locked_until:
        locked = user.locked_until
        if locked.tzinfo is None:
            from datetime import timezone

            locked = locked.replace(tzinfo=timezone.utc)
        if locked > now:
            dummy_verify(body.password)
            raise HTTPException(status_code=423, detail="Cuenta bloqueada temporalmente.")

    if user is None:
        dummy_verify(body.password)
        db.add(LoginAttempt(username=username[:64], ip=ip, success=False, created_at=now))
        db.commit()
        raise HTTPException(status_code=401, detail="Credenciales inválidas.")

    if not verify_password(body.password, user.password_hash):
        user.failed_attempts += 1
        if user.failed_attempts >= settings.login_max_attempts:
            user.locked_until = lock_until()
        db.add(LoginAttempt(username=username[:64], ip=ip, success=False, created_at=now))
        db.commit()
        raise HTTPException(status_code=401, detail="Credenciales inválidas.")

    user.failed_attempts = 0
    user.locked_until = None
    user.last_login_at = now
    user.last_login_ip = ip
    csrf = new_csrf()
    db.add(LoginAttempt(username=username[:64], ip=ip, success=True, created_at=now))
    db.commit()
    token = make_session_token({"uid": user.id, "role": user.role, "csrf": csrf})
    set_session_cookie(response, token)
    response.set_cookie(
        key="velar_csrf",
        value=csrf,
        httponly=False,
        samesite="lax",
        secure=settings.app_env == "production",
        max_age=settings.session_hours * 3600,
        path="/",
    )
    return {"ok": True, "username": user.username, "role": user.role, "csrf": csrf}


@router.post("/logout")
def logout(response: Response):
    clear_session_cookie(response)
    response.delete_cookie("velar_csrf", path="/", samesite="lax")
    return {"ok": True}
