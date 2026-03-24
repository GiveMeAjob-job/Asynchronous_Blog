import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_production_settings_require_non_placeholder_secrets():
    with pytest.raises(ValidationError):
        Settings(
            ENVIRONMENT="production",
            SECRET_KEY="your-secret-key-here",
            APP_BASE_URL="https://blog.example.com",
            ALLOWED_HOSTS=["blog.example.com"],
            ADMIN_EMAIL="owner@example.com",
            ADMIN_USERNAME="owner",
            ADMIN_PASSWORD="StrongPassword123",
            REQUIRE_EMAIL_VERIFICATION=False,
        )


def test_production_settings_require_real_hosts():
    with pytest.raises(ValidationError):
        Settings(
            ENVIRONMENT="production",
            SECRET_KEY="prod-secret-value",
            APP_BASE_URL="http://localhost:8000",
            ALLOWED_HOSTS=["*"],
            ADMIN_EMAIL="owner@example.com",
            ADMIN_USERNAME="owner",
            ADMIN_PASSWORD="StrongPassword123",
            REQUIRE_EMAIL_VERIFICATION=False,
        )


def test_cookie_security_defaults_follow_environment():
    development = Settings(ENVIRONMENT="development")
    production = Settings(
        ENVIRONMENT="production",
        SECRET_KEY="prod-secret-value",
        APP_BASE_URL="https://blog.example.com",
        ALLOWED_HOSTS=["blog.example.com"],
        ADMIN_EMAIL="owner@example.com",
        ADMIN_USERNAME="owner",
        ADMIN_PASSWORD="StrongPassword123",
        REQUIRE_EMAIL_VERIFICATION=False,
    )

    assert development.COOKIE_SECURE is False
    assert production.COOKIE_SECURE is True
