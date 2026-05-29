from typing import Any

from fastapi import HTTPException, status
import jwt
from jwt.exceptions import PyJWKClientError, PyJWTError

from app.platform.config import SettingsError, settings


AUTHENTICATE_HEADER = {"WWW-Authenticate": "Bearer"}
INVALID_CREDENTIALS_DETAIL = "Invalid authentication credentials"

_jwks_client: jwt.PyJWKClient | None = None
_jwks_client_url: str | None = None


def credentials_exception(detail: str = INVALID_CREDENTIALS_DETAIL) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers=AUTHENTICATE_HEADER,
    )


def get_jwks_client() -> jwt.PyJWKClient:
    global _jwks_client, _jwks_client_url

    jwks_url = settings.SUPABASE_JWKS_URL
    if _jwks_client is None or _jwks_client_url != jwks_url:
        _jwks_client = jwt.PyJWKClient(jwks_url)
        _jwks_client_url = jwks_url
    return _jwks_client


def decode_and_verify_jwt(token: str) -> dict[str, Any]:
    try:
        signing_key = get_jwks_client().get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            audience=settings.SUPABASE_JWT_AUDIENCE,
            issuer=settings.SUPABASE_JWT_ISSUER,
            options={"require": ["sub", "exp", "role"]},
        )
    except (SettingsError, PyJWKClientError, PyJWTError) as exc:
        raise credentials_exception() from exc
