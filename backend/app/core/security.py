"""Autenticación y controles básicos de seguridad (CS).

- Contraseñas: bcrypt (cost 12), nunca en claro.
- Sesión: cookie firmada HttpOnly + SameSite=Lax (anti CSRF básico en navegador).
- CSRF de doble envío para POST JSON (header X-CSRF-Token).
- Fuerza bruta: contador + bloqueo temporal por usuario e IP.
- Cabeceras: nosniff, frame deny, referrer estricto.
- SQL: solo ORM parametrizado (SQLAlchemy).
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from fastapi import HTTPException, Request, Response, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.core.config import get_settings

DUMMY_HASH = bcrypt.hashpw(b"velar-dummy-not-a-real-user", bcrypt.gensalt(rounds=12))


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def dummy_verify(plain: str) -> None:
    """Evita timing leaks cuando el usuario no existe."""
    bcrypt.checkpw(plain.encode("utf-8"), DUMMY_HASH)


def _serializer() -> URLSafeTimedSerializer:
    settings = get_settings()
    return URLSafeTimedSerializer(settings.app_secret, salt="velar-session-v1")


def make_session_token(payload: dict[str, Any]) -> str:
    return _serializer().dumps(payload)


def read_session_token(token: str) -> dict[str, Any] | None:
    settings = get_settings()
    max_age = settings.session_hours * 3600
    try:
        data = _serializer().loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(data, dict):
        return None
    return data


def new_csrf() -> str:
    return secrets.token_urlsafe(32)


def set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    secure = settings.app_env == "production"
    response.set_cookie(
        key="velar_session",
        value=token,
        httponly=True,
        samesite="lax",
        secure=secure,
        max_age=settings.session_hours * 3600,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie("velar_session", path="/", samesite="lax")


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return (request.client.host if request.client else "unknown")[:64]


def require_csrf(request: Request, session: dict[str, Any]) -> None:
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    header = request.headers.get("x-csrf-token") or ""
    expected = session.get("csrf") or ""
    if not expected or not header or not secrets.compare_digest(header, expected):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF inválido")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def lock_until() -> datetime:
    return utcnow() + timedelta(minutes=get_settings().login_lock_minutes)
