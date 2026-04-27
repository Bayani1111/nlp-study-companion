import pytest

from app.config import Settings


def clear_config_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in [
        "APP_ENV",
        "SECRET_KEY",
        "DEBUG",
        "LOG_LEVEL",
        "DATABASE_URL",
        "CORS_ORIGINS",
        "AUTH_COOKIE_SECURE",
        "AUTH_COOKIE_SAMESITE",
        "CSRF_COOKIE_SAMESITE",
    ]:
        monkeypatch.delenv(key, raising=False)


def test_development_defaults_are_local_friendly(monkeypatch: pytest.MonkeyPatch):
    clear_config_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("SECRET_KEY", "dev-secret")

    settings = Settings()

    assert settings.DEBUG is True
    assert settings.LOG_LEVEL == "DEBUG"
    assert settings.DATABASE_URL == "sqlite+aiosqlite:///./study_companion.db"
    assert settings.CORS_ORIGINS == ["http://localhost:8000", "http://127.0.0.1:8000"]
    assert settings.AUTH_COOKIE_SECURE is False
    assert settings.AUTH_COOKIE_SAMESITE == "lax"


def test_testing_defaults_use_test_database(monkeypatch: pytest.MonkeyPatch):
    clear_config_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "testing")
    monkeypatch.setenv("SECRET_KEY", "test-secret")

    settings = Settings()

    assert settings.DEBUG is True
    assert settings.LOG_LEVEL == "DEBUG"
    assert settings.DATABASE_URL == "sqlite+aiosqlite:///./test_study_companion.db"
    assert settings.AUTH_COOKIE_SECURE is False


def test_production_requires_secure_cookie_and_cors(monkeypatch: pytest.MonkeyPatch):
    clear_config_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "prod-secret")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@db:5432/app")

    with pytest.raises(RuntimeError, match="CORS_ORIGINS must be set in production."):
        Settings()

    monkeypatch.setenv("CORS_ORIGINS", "https://example.com")
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")

    with pytest.raises(RuntimeError, match="AUTH_COOKIE_SECURE must be true in production."):
        Settings()


def test_production_defaults_are_stricter(monkeypatch: pytest.MonkeyPatch):
    clear_config_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "prod-secret")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@db:5432/app")
    monkeypatch.setenv("CORS_ORIGINS", "https://example.com")

    settings = Settings()

    assert settings.DEBUG is False
    assert settings.LOG_LEVEL == "INFO"
    assert settings.AUTH_COOKIE_SECURE is True
    assert settings.AUTH_COOKIE_SAMESITE == "strict"
