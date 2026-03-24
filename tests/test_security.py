from jose import jwt

from app.core.config import settings
from app.core.security import (
    ACCESS_TOKEN_SCOPE,
    REFRESH_TOKEN_SCOPE,
    clear_auth_cookies,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    set_auth_cookies,
)
from fastapi import Response


def test_access_token_round_trip():
    token = create_access_token(subject=123, token_version=4)
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    assert payload["sub"] == "123"
    assert payload["scope"] == ACCESS_TOKEN_SCOPE
    assert payload["ver"] == 4
    assert "exp" in payload


def test_refresh_token_round_trip():
    token = create_refresh_token(subject=321, token_version=2, persistent=True)
    payload = decode_refresh_token(token)

    assert payload["sub"] == "321"
    assert payload["scope"] == REFRESH_TOKEN_SCOPE
    assert payload["ver"] == 2
    assert payload["persistent"] is True


def test_auth_cookie_helpers_manage_both_tokens():
    response = Response()
    set_auth_cookies(
        response,
        access_token="access-value",
        refresh_token="refresh-value",
        refresh_max_age=600,
    )
    headers = response.headers.getlist("set-cookie")

    assert any(settings.ACCESS_COOKIE_NAME in header for header in headers)
    assert any(settings.REFRESH_COOKIE_NAME in header for header in headers)

    clear_auth_cookies(response)
    cleared_headers = response.headers.getlist("set-cookie")

    assert any(f"{settings.ACCESS_COOKIE_NAME}=" in header and "Max-Age=0" in header for header in cleared_headers)
    assert any(f"{settings.REFRESH_COOKIE_NAME}=" in header and "Max-Age=0" in header for header in cleared_headers)
