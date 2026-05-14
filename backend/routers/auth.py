import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, status
import bcrypt
from jose import jwt
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.models.user import User
from backend.models.user_profile import UserProfile
from backend.schemas.auth import ChangePasswordRequest, LoginRequest, RegisterRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


def _hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _verify(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())

JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-env-local")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = 60


def _make_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "iss": "whai",
        "iat": now,
        "exp": now + timedelta(minutes=JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


_RESERVED_IDS = {"demo", "id123", "admin", "root", "system"}


@router.get("/check-id")
def check_id(user_id: str, db: Session = Depends(get_db)) -> dict:
    if user_id.lower() in _RESERVED_IDS:
        return {"available": False}
    try:
        exists = db.get(User, user_id) is not None
        return {"available": not exists}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"db_unavailable: {type(e).__name__}: {e}")


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, db: Session = Depends(get_db)) -> dict:
    if db.get(User, body.user_id):
        raise HTTPException(status_code=409, detail="이미 사용 중인 아이디입니다.")

    user = User(
        user_id=body.user_id,
        name=body.name,
        password_hash=_hash(body.password),
        birth_year=body.birth_year,
        gender=body.gender,
    )
    db.add(user)
    if body.invest_type:
        db.add(UserProfile(user_id=body.user_id, invest_type=body.invest_type))
    db.commit()
    return {"message": "회원가입이 완료되었습니다."}


def _get_user_id(authorization: str = Header(None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="인증이 필요합니다.")
    try:
        payload = jwt.decode(authorization.split(" ")[1], JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload["sub"]
    except Exception:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")


@router.get("/me")
def me(user_id: str = Depends(_get_user_id), db: Session = Depends(get_db)) -> dict:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    return {
        "user_id": user.user_id,
        "name": user.name,
        "birth_year": user.birth_year,
        "gender": user.gender,
        "created_at": user.created_at.strftime("%Y-%m-%d") if user.created_at else None,
    }


@router.post("/change-password")
def change_password(
    body: ChangePasswordRequest,
    user_id: str = Depends(_get_user_id),
    db: Session = Depends(get_db),
) -> dict:
    user = db.get(User, user_id)
    if not user or not _verify(body.current_password, user.password_hash):
        raise HTTPException(status_code=401, detail="현재 비밀번호가 올바르지 않습니다.")
    user.password_hash = _hash(body.new_password)
    db.commit()
    return {"message": "비밀번호가 변경되었습니다."}


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.get(User, body.user_id)
    if not user or not _verify(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 올바르지 않습니다.")

    return TokenResponse(
        access_token=_make_token(user.user_id),
        name=user.name,
        user_id=user.user_id,
    )
