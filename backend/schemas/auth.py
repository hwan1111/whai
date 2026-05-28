from pydantic import BaseModel, field_validator
from typing import Optional
import re


_RESERVED_IDS = {"demo", "id123", "admin", "root", "system"}


_INVEST_TYPES = {"SAFE", "STAB", "NEUT", "GROW", "AGGR"}


class RegisterRequest(BaseModel):
    user_id: str
    name: str
    password: str
    birth_year: Optional[int] = None
    gender: Optional[str] = None
    invest_type: Optional[str] = None

    @field_validator("invest_type")
    @classmethod
    def validate_invest_type(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _INVEST_TYPES:
            raise ValueError("invest_type은 SAFE, STAB, NEUT, GROW, AGGR 중 하나여야 합니다.")
        return v

    @field_validator("user_id")
    @classmethod
    def validate_user_id(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9]{5,20}$", v):
            raise ValueError("아이디는 영문·숫자만 사용 가능하며 5~20자여야 합니다.")
        if v.lower() in _RESERVED_IDS:
            raise ValueError("사용할 수 없는 아이디입니다.")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not (5 <= len(v) <= 20):
            raise ValueError("비밀번호는 5~20자여야 합니다.")
        return v

    @field_validator("gender")
    @classmethod
    def validate_gender(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ("M", "F"):
            raise ValueError("gender는 M, F, OTHER 중 하나여야 합니다.")
        return v


class LoginRequest(BaseModel):
    user_id: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        if not (5 <= len(v) <= 20):
            raise ValueError("비밀번호는 5~20자여야 합니다.")
        return v


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    name: str
    user_id: str
    profile_image_url: Optional[str] = None


class UpdateProfileRequest(BaseModel):
    name: Optional[str] = None
    invest_type: Optional[str] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not (1 <= len(v.strip()) <= 20):
            raise ValueError("이름은 1~20자여야 합니다.")
        return v.strip() if v else v

    @field_validator("invest_type")
    @classmethod
    def validate_invest_type(cls, v: Optional[str]) -> Optional[str]:
        _INVEST_TYPES = {"SAFE", "STAB", "NEUT", "GROW", "AGGR"}
        if v is not None and v not in _INVEST_TYPES:
            raise ValueError("올바르지 않은 투자성향입니다.")
        return v


class DeleteAccountRequest(BaseModel):
    password: str
