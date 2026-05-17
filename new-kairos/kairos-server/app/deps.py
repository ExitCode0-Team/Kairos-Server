"""
FastAPI dependencies — authentication via Supabase JWT.
"""

import logging
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError

from app.config import get_settings

logger = logging.getLogger(__name__)

_bearer = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> UUID:
    """
    Validate the Supabase JWT in the Authorization: Bearer header and return
    the authenticated user's UUID.

    The token is a standard HS256 JWT signed with the project's JWT Secret
    (Supabase Project Settings → API → JWT Settings).
    """
    settings = get_settings()

    if not settings.supabase_jwt_secret:
        raise HTTPException(
            status_code=500,
            detail="SUPABASE_JWT_SECRET is not configured on the server.",
        )

    token = credentials.credentials
    try:
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
            options={"verify_exp": True},
        )
    except ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired.")
    except InvalidTokenError as exc:
        logger.debug("JWT validation failed: %s", exc)
        raise HTTPException(status_code=401, detail="Invalid token.")

    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="Token missing sub claim.")

    try:
        return UUID(sub)
    except ValueError:
        raise HTTPException(status_code=401, detail="Token sub is not a valid UUID.")
