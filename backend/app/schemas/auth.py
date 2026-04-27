import re

from pydantic import BaseModel, EmailStr, field_validator


class RegisterRequest(BaseModel):
    username: str
    email: EmailStr
    password: str

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        if len(value) < 3 or len(value) > 50:
            raise ValueError("用户名长度必须在 3 到 50 个字符之间")
        if not re.fullmatch(r"[a-zA-Z0-9_]+", value):
            raise ValueError("用户名只能包含字母、数字和下划线")
        return value

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("密码长度不能少于 8 个字符")
        if not re.search(r"[a-zA-Z]", value):
            raise ValueError("密码必须包含字母")
        if not re.search(r"[0-9]", value):
            raise ValueError("密码必须包含数字")
        return value


class LoginRequest(BaseModel):
    username: str
    password: str


class UserProfile(BaseModel):
    id: int
    username: str
    email: str
    nickname: str | None = None
    avatar_url: str | None = None
    companion_tone_style: str | None = None
    companion_tone_locked: bool = False

    model_config = {"from_attributes": True}


class AuthResponse(BaseModel):
    access_token: str | None = None
    token_type: str = "bearer"
    user: UserProfile


class UserProfileUpdate(BaseModel):
    nickname: str | None = None
    avatar_url: str | None = None


class UserPreference(BaseModel):
    companion_tone_style: str = "gentle"
    companion_tone_source: str = "default"
    companion_tone_locked: bool = False
    companion_tone_manual_style: str | None = None
    companion_tone_effective_style: str = "gentle"
    companion_tone_source_detail: str = "default"
    response_density: str = "standard"
    response_density_source: str = "default"

    @field_validator("companion_tone_style")
    @classmethod
    def validate_companion_tone_style(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"gentle", "direct", "motivational"}:
            raise ValueError("语气风格仅支持 gentle / direct / motivational")
        return normalized

    @field_validator("companion_tone_source")
    @classmethod
    def validate_companion_tone_source(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"manual", "auto", "default"}:
            raise ValueError("语气来源仅支持 manual / auto / default")
        return normalized

    @field_validator("companion_tone_manual_style")
    @classmethod
    def validate_companion_tone_manual_style(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if normalized not in {"gentle", "direct", "motivational"}:
            raise ValueError("手动语气仅支持 gentle / direct / motivational")
        return normalized

    @field_validator("companion_tone_effective_style")
    @classmethod
    def validate_companion_tone_effective_style(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"gentle", "direct", "motivational"}:
            raise ValueError("生效语气仅支持 gentle / direct / motivational")
        return normalized

    @field_validator("companion_tone_source_detail")
    @classmethod
    def validate_companion_tone_source_detail(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"hard", "soft", "default"}:
            raise ValueError("语气来源明细仅支持 hard / soft / default")
        return normalized

    @field_validator("response_density")
    @classmethod
    def validate_response_density(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"concise", "standard", "detailed"}:
            raise ValueError("信息密度仅支持 concise / standard / detailed")
        return normalized

    @field_validator("response_density_source")
    @classmethod
    def validate_response_density_source(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"hard", "soft", "default"}:
            raise ValueError("信息密度来源仅支持 hard / soft / default")
        return normalized
