"""
Dashboard endpoint.

GET /v1/dashboard/summary — aggregated KPIs, recent matches, activity log
"""

import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.deps import get_current_user
from app.schemas import (
    Activity,
    DashboardStats,
    DashboardSummary,
    Match,
)
from app.supabase_client import get_supabase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
def get_dashboard_summary(user_id: UUID = Depends(get_current_user)) -> DashboardSummary:
    """
    Return aggregated dashboard data for the authenticated user:
    - KPI stats with deltas
    - 5 most recent matches
    - 10 most recent activity log entries
    """
    client = get_supabase()
    uid = str(user_id)

    try:
        # Matches today
        today_str = datetime.now(timezone.utc).date().isoformat()
        today_resp = (
            client.table("matches")
            .select("id", count="exact")
            .eq("user_id", uid)
            .gte("posted_at", today_str)
            .execute()
        )
        matches_today = today_resp.count or 0

        # New this week (last 7 days)
        from datetime import timedelta
        week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).date().isoformat()
        week_resp = (
            client.table("matches")
            .select("id", count="exact")
            .eq("user_id", uid)
            .gte("posted_at", week_ago)
            .execute()
        )
        new_this_week = week_resp.count or 0

        # Average match score
        scores_resp = (
            client.table("matches")
            .select("score")
            .eq("user_id", uid)
            .execute()
        )
        scores = [row["score"] for row in (scores_resp.data or [])]
        avg_score = round(sum(scores) / len(scores), 1) if scores else 0.0

        # Saved roles count
        saved_resp = (
            client.table("saved_matches")
            .select("match_id", count="exact")
            .eq("user_id", uid)
            .execute()
        )
        saved_roles = saved_resp.count or 0

        stats = DashboardStats(
            matchesToday=matches_today,
            newThisWeek=new_this_week,
            avgMatchScore=avg_score,
            savedRoles=saved_roles,
            deltas={},
        )

        # Recent matches (last 5, highest score first)
        saved_set: set[str] = {row["match_id"] for row in (
            client.table("saved_matches").select("match_id").eq("user_id", uid).execute().data or []
        )}
        applied_set: set[str] = {row["match_id"] for row in (
            client.table("applications").select("match_id").eq("user_id", uid).execute().data or []
        )}

        recent_resp = (
            client.table("matches")
            .select("id, company, role, location, posted_at, score, skills")
            .eq("user_id", uid)
            .order("score", desc=True)
            .limit(5)
            .execute()
        )
        recent_matches = [
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
            for row in (recent_resp.data or [])
        ]

        # Activities (most recent 10)
        activities_resp = (
            client.table("activities")
            .select("id, icon_key, label, at")
            .eq("user_id", uid)
            .order("at", desc=True)
            .limit(10)
            .execute()
        )
        activities = [
            Activity(
                id=UUID(row["id"]),
                iconKey=row["icon_key"],
                label=row["label"],
                at=row["at"],
            )
            for row in (activities_resp.data or [])
        ]

    except Exception as exc:
        logger.exception("Failed to compute dashboard summary for user %s", user_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return DashboardSummary(
        stats=stats,
        recentMatches=recent_matches,
        activities=activities,
    )
