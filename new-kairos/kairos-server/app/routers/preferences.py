"""
Job preferences endpoints.

GET /v1/preferences/jobs       — return the user's selected job tags
PUT /v1/preferences/jobs       — replace the selected tags
GET /v1/preferences/jobs/pool  — return the full vocabulary of available tags
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.deps import get_current_user
from app.schemas import JobPreferencesRequest, JobPreferencesResponse, JobTag, JobTagPoolResponse
from app.supabase_client import get_supabase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/preferences/jobs", tags=["preferences"])

# ---------------------------------------------------------------------------
# Server-owned vocabulary — replaces the old client-side job-tag-pool.ts
# ---------------------------------------------------------------------------

_MAX_TAGS = 10

_TAG_POOL: list[JobTag] = [
    JobTag(id="fullstack", label="Full Stack"),
    JobTag(id="frontend", label="Frontend"),
    JobTag(id="backend", label="Backend"),
    JobTag(id="mobile", label="Mobile"),
    JobTag(id="devops", label="DevOps / Platform"),
    JobTag(id="data-eng", label="Data Engineering"),
    JobTag(id="ml", label="Machine Learning"),
    JobTag(id="security", label="Security"),
    JobTag(id="qa", label="QA / Testing"),
    JobTag(id="product", label="Product Management"),
    JobTag(id="design", label="UI / UX Design"),
    JobTag(id="embedded", label="Embedded / Firmware"),
    JobTag(id="blockchain", label="Blockchain"),
    JobTag(id="game-dev", label="Game Development"),
    JobTag(id="sre", label="SRE / Infrastructure"),
    JobTag(id="cloud", label="Cloud Architecture"),
    JobTag(id="ai-eng", label="AI Engineering"),
    JobTag(id="research", label="Research"),
    JobTag(id="startup", label="Startup"),
    JobTag(id="remote", label="Remote Only"),
]

_VALID_IDS = {tag.id for tag in _TAG_POOL}


# ---------------------------------------------------------------------------
# GET /v1/preferences/jobs/pool
# ---------------------------------------------------------------------------

@router.get("/pool", response_model=JobTagPoolResponse)
def get_job_tag_pool(_user_id: UUID = Depends(get_current_user)) -> JobTagPoolResponse:
    """Return the full vocabulary of selectable job tags and the selection limit."""
    return JobTagPoolResponse(tags=_TAG_POOL, max=_MAX_TAGS)


# ---------------------------------------------------------------------------
# GET /v1/preferences/jobs
# ---------------------------------------------------------------------------

@router.get("", response_model=JobPreferencesResponse)
def get_job_preferences(user_id: UUID = Depends(get_current_user)) -> JobPreferencesResponse:
    """Return the authenticated user's selected job tags."""
    client = get_supabase()
    resp = (
        client.table("job_preferences")
        .select("tags")
        .eq("user_id", str(user_id))
        .limit(1)
        .execute()
    )
    tags: list[str] = []
    if resp.data:
        tags = resp.data[0].get("tags") or []
    return JobPreferencesResponse(tags=tags)


# ---------------------------------------------------------------------------
# PUT /v1/preferences/jobs
# ---------------------------------------------------------------------------

@router.put("", response_model=JobPreferencesResponse)
def put_job_preferences(
    body: JobPreferencesRequest,
    user_id: UUID = Depends(get_current_user),
) -> JobPreferencesResponse:
    """Replace the user's selected job tags. Max _MAX_TAGS tags, all must be valid pool IDs."""
    invalid = [t for t in body.tags if t not in _VALID_IDS]
    if invalid:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown tag IDs: {invalid}. Call GET /v1/preferences/jobs/pool for valid IDs.",
        )
    if len(body.tags) > _MAX_TAGS:
        raise HTTPException(
            status_code=422,
            detail=f"Maximum {_MAX_TAGS} tags allowed, got {len(body.tags)}.",
        )

    client = get_supabase()
    try:
        client.table("job_preferences").upsert(
            {"user_id": str(user_id), "tags": body.tags},
            on_conflict="user_id",
        ).execute()
    except Exception as exc:
        logger.exception("Failed to update job preferences for user %s", user_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return JobPreferencesResponse(tags=body.tags)
