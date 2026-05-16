"""
User projects endpoint.

Stores portfolio / project JSON on public.profiles.projects.
The frontend (or Kairo) can POST structured data per user_id; we will
tighten the schema later.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.deps import verify_api_secret
from app.schemas import UserProjectsPayload, UserProjectsResponse
from app.services.projects import upsert_user_projects

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/users", tags=["projects"])


@router.put(
    "/{user_id}/projects",
    response_model=UserProjectsResponse,
    dependencies=[Depends(verify_api_secret)],
    summary="Replace projects JSON for a user",
)
def put_user_projects(
    user_id: UUID,
    body: UserProjectsPayload,
) -> UserProjectsResponse:
    """
    Accept a JSON list of projects and save to `profiles.projects`.

    Example body:

    ```json
    {
      "projects": [
        {
          "name": "PayEase Dashboard",
          "role": "Full-Stack Developer",
          "bullets": ["Built React admin", "PostgreSQL APIs"]
        }
      ]
    }
    ```
    """
    try:
        stored = upsert_user_projects(user_id, body.projects)
    except Exception as exc:
        logger.exception("Failed to update projects for user %s", user_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return UserProjectsResponse(user_id=user_id, projects=stored)


@router.get(
    "/{user_id}/projects",
    response_model=UserProjectsResponse,
    dependencies=[Depends(verify_api_secret)],
    summary="Read projects JSON for a user",
)
def get_user_projects(user_id: UUID) -> UserProjectsResponse:
    """Return current profiles.projects for the user (empty list if no profile)."""
    from app.supabase_client import get_supabase

    client = get_supabase()
    row = (
        client.table("profiles")
        .select("projects")
        .eq("user_id", str(user_id))
        .execute()
    )

    projects: list = []
    if row.data and len(row.data) > 0:
        raw = row.data[0].get("projects")
        if raw is not None:
            projects = raw

    return UserProjectsResponse(
        user_id=user_id,
        projects=projects,
        message="ok",
    )
