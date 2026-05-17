"""
Connectors endpoints.

GET  /v1/connectors              — full catalog split by category
GET  /v1/connectors/status       — which connectors are connected + active channel
POST /v1/connectors/{id}/connect — mark a connector as connected (OAuth stub)
POST /v1/connectors/{id}/disconnect
PUT  /v1/connectors/channel      — set the active notification channel
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.deps import get_current_user
from app.schemas import (
    ChannelRequest,
    ChannelResponse,
    Connector,
    ConnectorActionResponse,
    ConnectorListResponse,
    ConnectorStatusResponse,
)
from app.supabase_client import get_supabase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/connectors", tags=["connectors"])

# ---------------------------------------------------------------------------
# Static catalog — icons live client-side, only text sent over the wire
# ---------------------------------------------------------------------------

_CATALOG: list[Connector] = [
    Connector(id="linkedin", name="LinkedIn", description="Import jobs and profile data", category="data"),
    Connector(id="github", name="GitHub", description="Showcase your repositories", category="data"),
    Connector(id="google-jobs", name="Google Jobs", description="Search millions of job listings", category="data"),
    Connector(id="whatsapp", name="WhatsApp", description="Get match alerts via WhatsApp", category="channel"),
    Connector(id="telegram", name="Telegram", description="Get match alerts via Telegram", category="channel"),
    Connector(id="slack", name="Slack", description="Get match alerts in Slack", category="channel"),
    Connector(id="discord", name="Discord", description="Get match alerts in Discord", category="channel"),
    Connector(id="email", name="Email", description="Get match alerts by email", category="channel"),
    Connector(id="glassdoor", name="Glassdoor", description="Company reviews & salaries", category="coming_soon"),
    Connector(id="indeed", name="Indeed", description="World's largest job site", category="coming_soon"),
    Connector(id="lever", name="Lever", description="ATS integration", category="coming_soon"),
]


# ---------------------------------------------------------------------------
# GET /v1/connectors
# ---------------------------------------------------------------------------

@router.get("", response_model=ConnectorListResponse)
def get_connectors(
    _user_id: UUID = Depends(get_current_user),
) -> ConnectorListResponse:
    """Return the full connector catalog grouped by category."""
    return ConnectorListResponse(
        dataSources=[c for c in _CATALOG if c.category == "data"],
        channels=[c for c in _CATALOG if c.category == "channel"],
        comingSoon=[c for c in _CATALOG if c.category == "coming_soon"],
    )


# ---------------------------------------------------------------------------
# GET /v1/connectors/status
# ---------------------------------------------------------------------------

@router.get("/status", response_model=ConnectorStatusResponse)
def get_connector_status(user_id: UUID = Depends(get_current_user)) -> ConnectorStatusResponse:
    """Return the set of connected connector IDs and the active channel."""
    client = get_supabase()

    connected_resp = (
        client.table("connectors_status")
        .select("connector_id")
        .eq("user_id", str(user_id))
        .execute()
    )
    channel_resp = (
        client.table("active_channel")
        .select("channel")
        .eq("user_id", str(user_id))
        .limit(1)
        .execute()
    )

    connected = [row["connector_id"] for row in (connected_resp.data or [])]
    active_channel = ""
    if channel_resp.data:
        active_channel = channel_resp.data[0]["channel"]

    return ConnectorStatusResponse(connected=connected, activeChannel=active_channel)


# ---------------------------------------------------------------------------
# POST /v1/connectors/{id}/connect
# ---------------------------------------------------------------------------

@router.post("/{connector_id}/connect", response_model=ConnectorActionResponse)
def connect_connector(
    connector_id: str,
    user_id: UUID = Depends(get_current_user),
) -> ConnectorActionResponse:
    """
    Mark a connector as connected.

    For OAuth-based connectors the response will include an `oauthUrl` to
    redirect the user to — currently returns `None` (stub).
    """
    known_ids = {c.id for c in _CATALOG if c.category != "coming_soon"}
    if connector_id not in known_ids:
        raise HTTPException(status_code=404, detail=f"Unknown connector: {connector_id!r}")

    client = get_supabase()
    try:
        client.table("connectors_status").upsert(
            {"user_id": str(user_id), "connector_id": connector_id},
            on_conflict="user_id,connector_id",
        ).execute()
    except Exception as exc:
        logger.exception("Failed to connect %s for user %s", connector_id, user_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return ConnectorActionResponse(connected=True, oauthUrl=None)


# ---------------------------------------------------------------------------
# POST /v1/connectors/{id}/disconnect
# ---------------------------------------------------------------------------

@router.post("/{connector_id}/disconnect", response_model=ConnectorActionResponse)
def disconnect_connector(
    connector_id: str,
    user_id: UUID = Depends(get_current_user),
) -> ConnectorActionResponse:
    """Remove a connector connection."""
    client = get_supabase()
    try:
        client.table("connectors_status").delete().eq("user_id", str(user_id)).eq(
            "connector_id", connector_id
        ).execute()
    except Exception as exc:
        logger.exception("Failed to disconnect %s for user %s", connector_id, user_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return ConnectorActionResponse(connected=False)


# ---------------------------------------------------------------------------
# PUT /v1/connectors/channel
# ---------------------------------------------------------------------------

@router.put("/channel", response_model=ChannelResponse)
def set_active_channel(
    body: ChannelRequest,
    user_id: UUID = Depends(get_current_user),
) -> ChannelResponse:
    """Set the user's active notification channel."""
    valid = {c.id for c in _CATALOG if c.category == "channel"}
    if body.channel not in valid:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid channel {body.channel!r}. Valid: {sorted(valid)}",
        )

    client = get_supabase()
    try:
        client.table("active_channel").upsert(
            {"user_id": str(user_id), "channel": body.channel},
            on_conflict="user_id",
        ).execute()
    except Exception as exc:
        logger.exception("Failed to set active channel for user %s", user_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return ChannelResponse(activeChannel=body.channel)
