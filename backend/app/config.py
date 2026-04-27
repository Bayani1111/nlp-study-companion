import os
from pathlib import Path

from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

_ENVIRONMENTS = {"development", "testing", "production"}


class Settings:
    """Centralized application settings loaded from environment variables."""

    def __init__(self) -> None:
        self.APP_ENV = self._get_app_env()
        self.DEBUG = self._get_bool(
            "DEBUG",
            default=self.APP_ENV in {"development", "testing"},
        )
        self.LOG_LEVEL = (
            os.getenv(
                "LOG_LEVEL",
                "DEBUG" if self.DEBUG else "INFO",
            )
            .strip()
            .upper()
        )
        self.SQL_ECHO = self._get_bool("SQL_ECHO", default=False)

        self.SECRET_KEY: str = os.getenv("SECRET_KEY", "").strip()
        self.JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
        self.JWT_EXPIRE_HOURS: int = int(os.getenv("JWT_EXPIRE_HOURS", "24"))

        self.DATABASE_URL: str = os.getenv(
            "DATABASE_URL",
            self._default_database_url(),
        ).strip()

        self.LLM_API_KEY: str = os.getenv("LLM_API_KEY", "").strip()
        self.LLM_API_BASE_URL: str = os.getenv(
            "LLM_API_BASE_URL",
            "https://api.openai.com/v1",
        ).strip()
        self.LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o-mini").strip()
        self.LLM_CHAT_MODEL: str = os.getenv(
            "LLM_CHAT_MODEL",
            self.LLM_MODEL,
        ).strip()
        self.LLM_EXTRACTION_MODEL: str = os.getenv(
            "LLM_EXTRACTION_MODEL",
            self.LLM_MODEL,
        ).strip()

        cors_origins = os.getenv("CORS_ORIGINS", self._default_cors_origins())
        self.CORS_ORIGINS: list[str] = [
            origin.strip().rstrip("/") for origin in cors_origins.split(",") if origin.strip()
        ]

        self.AUTH_COOKIE_NAME: str = os.getenv(
            "AUTH_COOKIE_NAME",
            "study_companion_session",
        ).strip()
        self.AUTH_COOKIE_SECURE: bool = self._get_bool(
            "AUTH_COOKIE_SECURE",
            default=self.APP_ENV == "production",
        )
        self.AUTH_COOKIE_MAX_AGE_SECONDS: int = self.JWT_EXPIRE_HOURS * 60 * 60
        self.AUTH_COOKIE_SAMESITE: str = (
            os.getenv(
                "AUTH_COOKIE_SAMESITE",
                "lax" if self.APP_ENV in {"development", "testing"} else "strict",
            )
            .strip()
            .lower()
        )

        self.CSRF_COOKIE_NAME: str = os.getenv(
            "CSRF_COOKIE_NAME",
            "study_companion_csrf",
        ).strip()
        self.CSRF_HEADER_NAME: str = os.getenv("CSRF_HEADER_NAME", "X-CSRF-Token").strip()
        self.CSRF_COOKIE_SAMESITE: str = (
            os.getenv(
                "CSRF_COOKIE_SAMESITE",
                self.AUTH_COOKIE_SAMESITE,
            )
            .strip()
            .lower()
        )

        self._validate()

    def _get_app_env(self) -> str:
        app_env = os.getenv("APP_ENV", "development").strip().lower()
        if app_env not in _ENVIRONMENTS:
            raise RuntimeError(f"APP_ENV must be one of {sorted(_ENVIRONMENTS)}, got: {app_env!r}")
        return app_env

    def _default_database_url(self) -> str:
        if self.APP_ENV == "testing":
            return "sqlite+aiosqlite:///./test_study_companion.db"
        return "sqlite+aiosqlite:///./study_companion.db"

    def _default_cors_origins(self) -> str:
        if self.APP_ENV in {"development", "testing"}:
            return "http://localhost:8000,http://127.0.0.1:8000"
        return ""

    @staticmethod
    def _get_bool(name: str, *, default: bool) -> bool:
        value = os.getenv(name)
        if value is None:
            return default
        return value.strip().lower() == "true"

    def _validate(self) -> None:
        if not self.SECRET_KEY:
            raise RuntimeError("SECRET_KEY is required. Set it in backend/.env or the environment.")

        if self.APP_ENV == "production":
            if not self.DATABASE_URL:
                raise RuntimeError("DATABASE_URL is required in production.")
            if not self.CORS_ORIGINS:
                raise RuntimeError("CORS_ORIGINS must be set in production.")
            if not self.AUTH_COOKIE_SECURE:
                raise RuntimeError("AUTH_COOKIE_SECURE must be true in production.")


settings = Settings()
