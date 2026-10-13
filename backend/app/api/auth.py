"""Authentication routes."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models import User
from app.schemas import Token, UserCreate, UserLogin, UserOut
from app.services.auth_service import (
    create_access_token,
    decode_token,
    hash_password,
    verify_password_or_dummy,
)
from app.services.rate_limit import login_rate_limit, register_rate_limit

router = APIRouter(prefix="/api/auth", tags=["auth"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

# Roles, from least to most privileged. Public signup may only ever assign
# VIEWER_ROLE; admin access requires an account seeded or promoted explicitly.
VIEWER_ROLE = "viewer"
ADMIN_ROLE = "admin"


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = db.query(User).filter(User.id == int(payload["sub"])).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def get_current_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != ADMIN_ROLE:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


@router.post("/register", response_model=Token)
def register(
    payload: UserCreate,
    db: Session = Depends(get_db),
    _rate: object = Depends(register_rate_limit),
):
    """Self-service signup.

    New accounts are always created with the least-privileged `viewer` role.
    Public registration must never be able to mint an administrator, otherwise
    anyone who can reach this endpoint owns the whole system. Admin accounts are
    provisioned by the startup seed (`DEMO_ADMIN_EMAIL`) or by promoting a user
    directly in the database.
    """
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(
        name=payload.name,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=VIEWER_ROLE,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(user.id, user.role)
    return Token(access_token=token, user=UserOut.model_validate(user))


@router.post("/login", response_model=Token)
def login(
    payload: UserLogin,
    db: Session = Depends(get_db),
    _rate: object = Depends(login_rate_limit),
):
    user = db.query(User).filter(User.email == payload.email).first()
    # Whether or not the email exists, password verification runs and the same
    # generic 401 is returned. When the account is absent (or its stored hash is
    # empty) the check runs against a fixed dummy hash, so the bcrypt work -- and
    # therefore the response time -- does not reveal whether the account exists.
    stored_hash = user.password_hash if user is not None else None
    if not verify_password_or_dummy(payload.password, stored_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token(user.id, user.role)
    return Token(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return UserOut.model_validate(user)