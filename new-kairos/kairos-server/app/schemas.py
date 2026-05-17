"""Pydantic request / response models for Kairos API v1."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Shared error envelope (FastAPI's default validation errors are overridden
# in main.py to match this shape)
# ---------------------------------------------------------------------------

class ApiError(BaseModel):
    error: str
    message: str | None = None
    field_errors: dict[str, list[str]] | None = Field(default=None, alias="fieldErrors")

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    ok: bool = True
    version: str = "0.1.0"


# ---------------------------------------------------------------------------
# UserProfile  (maps to public.profiles)
# ---------------------------------------------------------------------------

class UserProfile(BaseModel):
    name: str = ""
    role: str = ""
    skills: list[str] = Field(default_factory=list)
    experience: str = ""          # stored as experience_summary in DB
    projects: list[str] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)


class UserProfilePatch(BaseModel):
    name: str | None = None
    role: str | None = None
    skills: list[str] | None = None
    experience: str | None = None
    projects: list[str] | None = None
    references: list[str] | None = None


class UserProfilePutResponse(BaseModel):
    ok: bool = True


# ---------------------------------------------------------------------------
# CV extraction internals (kept for the extraction pipeline)
# ---------------------------------------------------------------------------

class CVExperience(BaseModel):
    company: str
    title: str
    start_date: str | None = None
    end_date: str | None = None
    current: bool = False
    description: str | None = None


class CVEducation(BaseModel):
    institution: str
    degree: str | None = None
    field: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    gpa: str | None = None


class CVLinks(BaseModel):
    linkedin: str | None = None
    github: str | None = None
    portfolio: str | None = None


class StructuredCV(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    summary: str | None = None
    skills: list[str] = Field(default_factory=list)
    experience: list[CVExperience] = Field(default_factory=list)
    education: list[CVEducation] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    links: CVLinks = Field(default_factory=CVLinks)


# ---------------------------------------------------------------------------
# Cv  (public-facing CV file record, maps to public.cvs)
# ---------------------------------------------------------------------------

class Cv(BaseModel):
    id: UUID
    name: str
    uploaded_at: datetime = Field(alias="uploadedAt")
    is_default: bool = Field(alias="isDefault")
    size_bytes: int = Field(alias="sizeBytes")

    model_config = {"populate_by_name": True}


class CvListResponse(BaseModel):
    items: list[Cv]


# ---------------------------------------------------------------------------
# Match  (maps to public.matches + saved/applied joins)
# ---------------------------------------------------------------------------

class Match(BaseModel):
    id: UUID
    company: str
    role: str
    location: str
    posted_at: datetime = Field(alias="postedAt")
    score: int
    skills: list[str]
    saved: bool = False
    applied: bool = False

    model_config = {"populate_by_name": True}


class MatchListResponse(BaseModel):
    items: list[Match]
    total: int
    page: int
    page_size: int = Field(alias="pageSize")

    model_config = {"populate_by_name": True}


class BookmarkRequest(BaseModel):
    saved: bool


class BookmarkResponse(BaseModel):
    saved: bool


class ApplyResponse(BaseModel):
    ok: bool = True
    application_id: UUID = Field(alias="applicationId")

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# Connector  (catalog item)
# ---------------------------------------------------------------------------

class Connector(BaseModel):
    id: str
    name: str
    description: str
    category: Literal["data", "channel", "coming_soon"]


class ConnectorListResponse(BaseModel):
    data_sources: list[Connector] = Field(alias="dataSources")
    channels: list[Connector]
    coming_soon: list[Connector] = Field(alias="comingSoon")

    model_config = {"populate_by_name": True}


class ConnectorStatusResponse(BaseModel):
    connected: list[str]
    active_channel: str = Field(alias="activeChannel", default="")

    model_config = {"populate_by_name": True}


class ConnectorActionResponse(BaseModel):
    connected: bool
    oauth_url: str | None = Field(alias="oauthUrl", default=None)

    model_config = {"populate_by_name": True}


class ChannelRequest(BaseModel):
    channel: str


class ChannelResponse(BaseModel):
    active_channel: str = Field(alias="activeChannel")

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

class DashboardStats(BaseModel):
    matches_today: int = Field(alias="matchesToday", default=0)
    new_this_week: int = Field(alias="newThisWeek", default=0)
    avg_match_score: float = Field(alias="avgMatchScore", default=0.0)
    saved_roles: int = Field(alias="savedRoles", default=0)
    deltas: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class Activity(BaseModel):
    id: UUID
    icon_key: Literal["match", "apply", "save", "cv", "agent"] = Field(alias="iconKey")
    label: str
    at: datetime

    model_config = {"populate_by_name": True}


class DashboardSummary(BaseModel):
    stats: DashboardStats
    recent_matches: list[Match] = Field(alias="recentMatches")
    activities: list[Activity]

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# Settings  (maps to public.user_settings)
# ---------------------------------------------------------------------------

class Settings(BaseModel):
    display_name: str = Field(alias="displayName", default="")
    email: str = ""
    notification_channel: Literal["whatsapp", "telegram", "slack", "discord", "email"] = Field(
        alias="notificationChannel", default="email"
    )

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# Job preferences  (maps to public.job_preferences)
# ---------------------------------------------------------------------------

class JobTag(BaseModel):
    id: str
    label: str


class JobPreferencesResponse(BaseModel):
    tags: list[str]


class JobTagPoolResponse(BaseModel):
    tags: list[JobTag]
    max: int = 10


class JobPreferencesRequest(BaseModel):
    tags: list[str]
