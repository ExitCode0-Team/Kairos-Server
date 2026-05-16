"""Pydantic request / response models."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    ok: bool = True
    service: str = "kairos-server"


# ---------------------------------------------------------------------------
# Extract request
# ---------------------------------------------------------------------------


class ExtractRequest(BaseModel):
    """
    Point to a PDF already uploaded to the cv-uploads Storage bucket.

    storage_path is the path inside the bucket, e.g. "{user_id}/my-cv.pdf"
    """

    user_id: UUID
    storage_path: str = Field(
        description="Path inside the cv-uploads bucket, e.g. '{user_id}/my-cv.pdf'"
    )


# ---------------------------------------------------------------------------
# Structured CV (MiniMax output)
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
# Responses
# ---------------------------------------------------------------------------


class ExtractResponse(BaseModel):
    """Response from POST /api/v1/extract"""

    user_id: UUID
    storage_path: str
    extract_method: Literal["pymupdf", "ocr"]
    char_count: int
    cv: StructuredCV


class CVDataResponse(BaseModel):
    """Response from GET /api/v1/users/{user_id}/cv"""

    user_id: UUID
    storage_path: str
    parsed_at: datetime
    model_used: str | None = None
    cv: StructuredCV


# ---------------------------------------------------------------------------
# Projects (unchanged)
# ---------------------------------------------------------------------------


class UserProjectsPayload(BaseModel):
    projects: list[Any] = Field(default_factory=list)


class UserProjectsResponse(BaseModel):
    user_id: UUID
    projects: list[Any]
    message: str = "projects updated"
