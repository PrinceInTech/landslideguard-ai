"""Authentication service: password hashing + JWT tokens.

Password hashing uses the `bcrypt` library directly. `passlib` is unmaintained
and its backend-detection code is incompatible with bcrypt >= 4.1/5.x (it raises
"password cannot be longer than 72 bytes" while probing the backend), which
broke all login and seeding. Hashes stay in the standard modular-crypt `$2b$`
format, so previously generated hashes remain valid.
"""
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import settings

# bcrypt only consumes the first 72 bytes of the secret; truncate explicitly so
# long passwords behave predictably instead of raising.
_BCRYPT_MAX_BYTES = 72


def _to_secret(password: str) -> bytes:
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def seed_default_admin(db: Session) -> None:
    """Idempotently create the demo admin user on a fresh database."""
    from app.models import User

    if db.query(User).filter(User.email == settings.DEMO_ADMIN_EMAIL).first():
        return
    admin = User(
        name="System Administrator",
        email=settings.DEMO_ADMIN_EMAIL,
        password_hash=hash_password(settings.DEMO_ADMIN_PASSWORD),
        role="admin",
    )
    db.add(admin)
    db.commit()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_to_secret(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(_to_secret(plain), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: int, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {"sub": str(user_id), "role": role, "exp": expire}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None