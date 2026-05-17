"""
Settings endpoints.

GET /v1/settings   — return the user's display settings
PUT /v1/settings   — replace settings
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.deps import get_current_user
from app.schemas import Settings
from app.supabase_client import get_supabase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/settings", tags=["settings"])


def _fetch_settings(user_id: UUID) -> Settings:
    client = get_supabase()

    settings_resp = (
        client.table("user_settings")
        .select("display_name, notification_channel")
        .eq("user_id", str(user_id))
        .limit(1)
        .execute()
    )
    profile_resp = (
        client.table("profiles")
        .select("email")
        .eq("user_id", str(user_id))
        .limit(1)
        .execute()
    )

    email = ""
    if profile_resp.data:
        email = profile_resp.data[0].get("email") or ""

    if not settings_resp.data:
        return Settings(displayName="", email=email, notificationChannel="email")

    row = settings_resp.data[0]
    return Settings(
        displayName=row.get("display_name") or "",
        email=email,
        notificationChannel=row.get("notification_channel") or "email",
    )


# ---------------------------------------------------------------------------
# GET /v1/settings
# ---------------------------------------------------------------------------

@router.get("", response_model=Settings)
def get_settings_endpoint(user_id: UUID = Depends(get_current_user)) -> Settings:
    """Return the authenticated user's settings."""
    return _fetch_settings(user_id)


# ---------------------------------------------------------------------------
# PUT /v1/settings
# ---------------------------------------------------------------------------

@router.put("", response_model=Settings)
def put_settings(
    body: Settings,
    user_id: UUID = Depends(get_current_user),
) -> Settings:
    """Replace the user's settings."""
    client = get_supabase()

    try:
        client.table("user_settings").upsert(
            {
                "user_id": str(user_id),
                "display_name": body.display_name,
                "notification_channel": body.notification_channel,
            },
            on_conflict="user_id",
        ).execute()

        # Keep email in sync with profiles table
        if body.email:
            client.table("profiles").upsert(
                {"user_id": str(user_id), "email": body.email},
                on_conflict="user_id",
            ).execute()
    except Exception as exc:
        logger.exception("Failed to update settings for user %s", user_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return _fetch_settings(user_id)
