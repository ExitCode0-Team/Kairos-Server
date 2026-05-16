"""
Update user project data in Supabase profiles.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.supabase_client import get_supabase


def upsert_user_projects(user_id: UUID, projects: list[Any]) -> list[Any]:
    """
    Write projects JSON into public.profiles for the given user.

    Ensures a profile row exists (upsert on user_id unique key).
    """
    client = get_supabase()

    payload = {
        "user_id": str(user_id),
        "projects": projects,
    }

    result = (
        client.table("profiles")
        .upsert(payload, on_conflict="user_id")
        .execute()
    )

    if not result.data:
        # Fetch back what we stored
        read = (
            client.table("profiles")
            .select("projects")
            .eq("user_id", str(user_id))
            .single()
            .execute()
        )
        if read.data:
            return read.data.get("projects") or []
        return projects

    return result.data[0].get("projects", projects)
