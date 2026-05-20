import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, File, Header, HTTPException, Request, UploadFile, status
import bcrypt
from jose import jwt
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.models.user import User
from backend.schemas.auth import ChangePasswordRequest, DeleteAccountRequest, LoginRequest, RegisterRequest, TokenResponse, UpdateProfileRequest

_S3_BUCKET = os.getenv("AWS_S3_BUCKET", "whai-profile-images")
_S3_REGION = os.getenv("AWS_DEFAULT_REGION", "ap-northeast-2")

def _s3_client():
    return boto3.client("s3", region_name=_S3_REGION)

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
        invest_type=body.invest_type,
    )
    db.add(user)
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
        "invest_type": user.invest_type,
        "created_at": user.created_at.strftime("%Y-%m-%d") if user.created_at else None,
        "profile_image_url": user.profile_image_url,
    }


@router.patch("/me")
def update_profile(
    body: UpdateProfileRequest,
    user_id: str = Depends(_get_user_id),
    db: Session = Depends(get_db),
) -> dict:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    if body.name is not None:
        user.name = body.name
    if body.invest_type is not None:
        user.invest_type = body.invest_type
    db.commit()
    return {"message": "프로필이 업데이트되었습니다.", "name": user.name, "invest_type": user.invest_type}


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


_ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


def _s3_key(user_id: str, ext: str) -> str:
    return f"profile_images/{user_id}_{uuid.uuid4().hex[:8]}{ext}"


def _s3_delete(key: str) -> None:
    try:
        _s3_client().delete_object(Bucket=_S3_BUCKET, Key=key)
    except ClientError:
        pass


@router.post("/me/profile-image")
async def upload_profile_image(
    file: UploadFile = File(...),
    user_id: str = Depends(_get_user_id),
    db: Session = Depends(get_db),
) -> dict:
    if file.content_type not in _ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="JPG, PNG, WEBP, GIF만 업로드 가능합니다.")

    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="파일 크기는 5MB 이하여야 합니다.")

    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    # 기존 S3 오브젝트 삭제
    if user.profile_image_url and ".amazonaws.com/" in user.profile_image_url:
        old_key = user.profile_image_url.split(".amazonaws.com/", 1)[-1]
        _s3_delete(old_key)

    ext = Path(file.filename).suffix.lower() or ".jpg"
    key = _s3_key(user_id, ext)

    try:
        _s3_client().put_object(
            Bucket=_S3_BUCKET,
            Key=key,
            Body=content,
            ContentType=file.content_type,
        )
    except ClientError as e:
        raise HTTPException(status_code=500, detail=f"이미지 업로드에 실패했습니다: {e}")

    image_url = f"https://{_S3_BUCKET}.s3.{_S3_REGION}.amazonaws.com/{key}"
    user.profile_image_url = image_url
    user.original_file_name = file.filename
    db.commit()

    return {"profile_image_url": image_url}


@router.delete("/me/profile-image", status_code=status.HTTP_204_NO_CONTENT)
def delete_profile_image(
    user_id: str = Depends(_get_user_id),
    db: Session = Depends(get_db),
) -> None:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    if user.profile_image_url and ".amazonaws.com/" in user.profile_image_url:
        old_key = user.profile_image_url.split(".amazonaws.com/", 1)[-1]
        _s3_delete(old_key)
    user.profile_image_url = None
    user.original_file_name = None
    db.commit()


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    body: DeleteAccountRequest,
    user_id: str = Depends(_get_user_id),
    db: Session = Depends(get_db),
) -> None:
    user = db.get(User, user_id)
    if not user or not _verify(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="비밀번호가 올바르지 않습니다.")
    db.delete(user)
    db.commit()


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.get(User, body.user_id)
    if not user or not _verify(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 올바르지 않습니다.")

    return TokenResponse(
        access_token=_make_token(user.user_id),
        name=user.name,
        user_id=user.user_id,
        profile_image_url=user.profile_image_url,
    )
