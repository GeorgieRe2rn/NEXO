from __future__ import annotations

import logging
import secrets
import string
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_password, utcnow
from app.infrastructure.db.models import User

logger = logging.getLogger(__name__)


def _credentials_path() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "admin_credentials.txt"


def _generate_password() -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*-_=+"
    while True:
        pwd = "".join(secrets.choice(alphabet) for _ in range(28))
        if (
            any(c.islower() for c in pwd)
            and any(c.isupper() for c in pwd)
            and any(c.isdigit() for c in pwd)
            and any(c in "!@#$%^&*-_=+" for c in pwd)
        ):
            return pwd


def bootstrap_admin(db: Session) -> None:
    settings = get_settings()
    existing = db.query(User).filter(User.username == settings.admin_username).one_or_none()
    if existing:
        return
    password = _generate_password()
    user = User(
        username=settings.admin_username,
        password_hash=hash_password(password),
        role="admin",
        failed_attempts=0,
        created_at=utcnow(),
    )
    db.add(user)
    db.commit()
    path = _credentials_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        (
            "VELAR · credenciales de administrador\n"
            "Guarda este archivo fuera del repositorio.\n\n"
            f"usuario: {settings.admin_username}\n"
            f"contraseña: {password}\n"
        ),
        encoding="utf-8",
    )
    logger.warning("Admin creado. Credenciales en %s", path)
