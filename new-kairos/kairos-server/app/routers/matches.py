"""
Matches endpoints.

GET  /v1/matches                      — paginated, filtered list of job matches
POST /v1/matches/{id}/bookmark        — save or unsave a match
POST /v1/matches/{id}/apply           — record an application
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.deps import get_current_user
from app.schemas import (
    ApplyResponse,
    BookmarkRequest,
    BookmarkResponse,
    Match,
    MatchListResponse,
)
from app.supabase_client import get_supabase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/matches", tags=["matches"])


# ---------------------------------------------------------------------------
# GET /v1/matches
# ---------------------------------------------------------------------------

@router.get("", response_model=MatchListResponse)
def get_matches(
    tab: str = Query(default="all", pattern="^(all|high|new)$"),
    sort: str = Query(default="match", pattern="^(match|recent|score)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100, alias="pageSize"),
    q: str = Query(default=""),
    user_id: UUID = Depends(get_current_user),
) -> MatchListResponse:
    """
    Return a paginated list of job matches for the authenticated user.

    - `tab=all` — all matches; `tab=high` — score ≥ 80; `tab=new` — posted today
    - `sort=match|recent|score`
    - `q` — case-insensitive substring search on company or role
    """
    client = get_supabase()

    # Fetch matches with saved/applied status
    query = (
        client.table("matches")
        .select(
            "id, company, role, location, posted_at, score, skills, "
            "saved_matches!left(user_id), applications!left(id)"
        )
        .eq("user_id", str(user_id))
    )

    if tab == "high":
        query = query.gte("score", 80)
    elif tab == "new":
        query = query.gte("posted_at", "now()::date")

    if q:
        query = query.or_(f"company.ilike.%{q}%,role.ilike.%{q}%")

    sort_col = {"match": "score", "recent": "posted_at", "score": "score"}.get(sort, "score")
    query = query.order(sort_col, desc=True)

    # Count total for pagination
    count_query = client.table("matches").select("id", count="exact").eq("user_id", str(user_id))
    if tab == "high":
        count_query = count_query.gte("score", 80)
    elif tab == "new":
        count_query = count_query.gte("posted_at", "now()::date")
    if q:
        count_query = count_query.or_(f"company.ilike.%{q}%,role.ilike.%{q}%")

    count_resp = count_query.execute()
    total = count_resp.count or 0

    offset = (page - 1) * page_size
    query = query.range(offset, offset + page_size - 1)
    resp = query.execute()

    saved_set: set[str] = set()
    applied_set: set[str] = set()
    saved_resp = (
        client.table("saved_matches")
        .select("match_id")
        .eq("user_id", str(user_id))
        .execute()
    )
    applied_resp = (
        client.table("applications")
        .select("match_id")
        .eq("user_id", str(user_id))
        .execute()
    )
    if saved_resp.data:
        saved_set = {row["match_id"] for row in saved_resp.data}
    if applied_resp.data:
        applied_set = {row["match_id"] for row in applied_resp.data}

    items: list[Match] = []
    for row in (resp.data or []):
        items.append(
            Match(
                id=UUID(row["id"]),
                company=row["company"],
                role=row["role"],
                location=row.get("location") or "",
                postedAt=row["posted_at"],
                score=row["score"],
                skills=row.get("skills") or [],
                saved=row["id"] in saved_set,
                applied=row["id"] in applied_set,
            )
        )

    return MatchListResponse(
        items=items,
        total=total,
        page=page,
        pageSize=page_size,
    )


# ---------------------------------------------------------------------------
# POST /v1/matches/{id}/bookmark
# ---------------------------------------------------------------------------

@router.post("/{match_id}/bookmark", response_model=BookmarkResponse)
def bookmark_match(
    match_id: UUID,
    body: BookmarkRequest,
    user_id: UUID = Depends(get_current_user),
) -> BookmarkResponse:
    """Save or unsave a match."""
    client = get_supabase()

    if body.saved:
        try:
            client.table("saved_matches").upsert(
                {"user_id": str(user_id), "match_id": str(match_id)},
                on_conflict="user_id,match_id",
            ).execute()
        except Exception as exc:
            logger.exception("Failed to bookmark match %s for user %s", match_id, user_id)
            raise HTTPException(status_code=500, detail=str(exc)) from exc
    else:
        try:
            client.table("saved_matches").delete().eq("user_id", str(user_id)).eq(
                "match_id", str(match_id)
            ).execute()
        except Exception as exc:
            logger.exception("Failed to unbookmark match %s for user %s", match_id, user_id)
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    return BookmarkResponse(saved=body.saved)


# ---------------------------------------------------------------------------
# POST /v1/matches/{id}/apply
# ---------------------------------------------------------------------------

@router.post("/{match_id}/apply", response_model=ApplyResponse)
def apply_match(
    match_id: UUID,
    user_id: UUID = Depends(get_current_user),
) -> ApplyResponse:
    """Record an application for a match. Idempotent — applying twice returns the same record."""
    client = get_supabase()

    # Check if already applied
    existing = (
        client.table("applications")
        .select("id")
        .eq("user_id", str(user_id))
        .eq("match_id", str(match_id))
        .limit(1)
        .execute()
    )
    if existing.data:
        return ApplyResponse(applicationId=UUID(existing.data[0]["id"]))

    try:
        resp = (
            client.table("applications")
            .insert({"user_id": str(user_id), "match_id": str(match_id)})
            .execute()
        )
        app_id = UUID(resp.data[0]["id"])
    except Exception as exc:
        logger.exception("Failed to record application for match %s user %s", match_id, user_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    # Log activity
    try:
        client.table("activities").insert(
            {
                "user_id": str(user_id),
                "icon_key": "apply",
                "label": f"Applied to match",
            }
        ).execute()
    except Exception:
        logger.warning("Failed to log apply activity for user %s", user_id)

    return ApplyResponse(applicationId=app_id)
