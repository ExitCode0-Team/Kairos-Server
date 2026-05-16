"""
FastAPI dependencies (auth, settings).
"""

from fastapi import Header, HTTPException

from app.config import get_settings


def verify_api_secret(x_api_secret: str | None = Header(default=None)) -> None:
    """
    Optional shared-secret guard.

    When API_SECRET is set in the environment, every request must send:
      X-API-Secret: <API_SECRET>

    Leave API_SECRET empty in .env for local development without headers.
    """
    expected = get_settings().api_secret
    if not expected:
        return
    if x_api_secret != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Secret")
