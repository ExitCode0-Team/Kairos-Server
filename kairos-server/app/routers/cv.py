"""
GET /api/v1/users/{user_id}/cv

Returns the stored structured CV for a given user from public.cv_data.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.deps import verify_api_secret
from app.schemas import CVDataResponse, StructuredCV

from app.supabase_client import get_supabase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["cv"])


@router.get(
    "/users/{user_id}/cv",
    response_model=CVDataResponse,
    dependencies=[Depends(verify_api_secret)],
    summary="Get structured CV data for a user",
)
def get_cv(user_id: UUID) -> CVDataResponse:
    """
    Return the latest parsed CV for `user_id`.

    Returns **404** if the user hasn't had a CV processed yet —
    run `POST /api/v1/extract` first.
    """
    client = get_supabase()

    resp = (
        client.table("cv_data")
        .select("user_id, storage_path, structured_json, model_used, parsed_at")
        .eq("user_id", str(user_id))
        .order("parsed_at", desc=True)
        .limit(1)
        .execute()
    )

    if not resp.data:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No CV data found for user {user_id}. "
                "Upload a PDF to Storage then call POST /api/v1/extract."
            ),
        )

    row = resp.data[0]

    try:
        cv = StructuredCV.model_validate(row["structured_json"])
    except Exception as exc:
        logger.exception("Stored CV data failed validation for user %s", user_id)
        raise HTTPException(status_code=500, detail=f"Stored CV data is malformed: {exc}") from exc

    return CVDataResponse(
        user_id=UUID(row["user_id"]),
        storage_path=row["storage_path"],
        parsed_at=row["parsed_at"],
        model_used=row.get("model_used"),
        cv=cv,
    )
