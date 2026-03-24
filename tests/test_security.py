from jose import jwt

from app.core.config import settings
from app.core.security import create_access_token


def test_access_token_round_trip():
    token = create_access_token(subject=123)
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    assert payload["sub"] == "123"
    assert "exp" in payload
