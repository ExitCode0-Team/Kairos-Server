"""
Profile endpoints.

GET   /v1/profile         — return the authenticated user's profile
PUT   /v1/profile         — replace the full profile
PATCH /v1/profile         — partially update the profile
POST  /v1/profile/cv      — upload PDF, parse it, and update profile skills/experience
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile

from app.config import get_settings
from app.deps import get_current_user
from app.schemas import (
    StructuredCV,
    UserProfile,
    UserProfilePatch,
    UserProfilePutResponse,
)
from app.services.extraction import extract_text_from_pdf
from app.services.minimax import parse_cv_with_minimax
from app.services.storage import upload_cv_pdf
from app.supabase_client import get_supabase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/profile", tags=["profile"])

_PDF_CONTENT_TYPES = {"application/pdf", "application/octet-stream", "binary/octet-stream"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row_to_profile(row: dict) -> UserProfile:
    projects_raw = row.get("projects") or []
    if isinstance(projects_raw, list):
        projects = [str(p) if not isinstance(p, str) else p for p in projects_raw]
    else:
        projects = []

    return UserProfile(
        name=row.get("full_name") or "",
        role=row.get("job_title") or "",
        skills=row.get("skills") or [],
        experience=row.get("experience_summary") or "",
        projects=projects,
        references=row.get("references_list") or [],
    )


def _fetch_profile(user_id: UUID) -> UserProfile:
    client = get_supabase()
    resp = (
        client.table("profiles")
        .select("full_name, job_title, skills, experience_summary, projects, references_list")
        .eq("user_id", str(user_id))
        .limit(1)
        .execute()
    )
    if not resp.data:
        return UserProfile()
    return _row_to_profile(resp.data[0])


def _upsert_profile(user_id: UUID, profile: UserProfile) -> None:
    client = get_supabase()
    client.table("profiles").upsert(
        {
            "user_id": str(user_id),
            "full_name": profile.name,
            "job_title": profile.role,
            "skills": profile.skills,
            "experience_summary": profile.experience,
            "projects": profile.projects,
            "references_list": profile.references,
        },
        on_conflict="user_id",
    ).execute()


# ---------------------------------------------------------------------------
# GET /v1/profile
# ---------------------------------------------------------------------------

@router.get("", response_model=UserProfile)
def get_profile(user_id: UUID = Depends(get_current_user)) -> UserProfile:
    """Return the authenticated user's profile. Returns empty defaults if no profile exists yet."""
    return _fetch_profile(user_id)


# ---------------------------------------------------------------------------
# PUT /v1/profile
# ---------------------------------------------------------------------------

@router.put("", response_model=UserProfilePutResponse)
def put_profile(
    body: UserProfile,
    user_id: UUID = Depends(get_current_user),
) -> UserProfilePutResponse:
    """Replace the full profile. All fields required; use PATCH for partial updates."""
    try:
        _upsert_profile(user_id, body)
    except Exception as exc:
        logger.exception("Failed to upsert profile for user_id=%s", user_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return UserProfilePutResponse()


# ---------------------------------------------------------------------------
# PATCH /v1/profile
# ---------------------------------------------------------------------------

@router.patch("", response_model=UserProfile)
def patch_profile(
    body: UserProfilePatch,
    user_id: UUID = Depends(get_current_user),
) -> UserProfile:
    """Partially update the profile. Only provided fields are changed."""
    current = _fetch_profile(user_id)

    updated = UserProfile(
        name=body.name if body.name is not None else current.name,
        role=body.role if body.role is not None else current.role,
        skills=body.skills if body.skills is not None else current.skills,
        experience=body.experience if body.experience is not None else current.experience,
        projects=body.projects if body.projects is not None else current.projects,
        references=body.references if body.references is not None else current.references,
    )

    try:
        _upsert_profile(user_id, updated)
    except Exception as exc:
        logger.exception("Failed to patch profile for user_id=%s", user_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return updated


# ---------------------------------------------------------------------------
# POST /v1/profile/cv
# ---------------------------------------------------------------------------

@router.post("/cv", response_model=UserProfile)
async def post_profile_cv(
    request: Request,
    user_id: UUID = Depends(get_current_user),
    file: UploadFile = File(default=None, description="PDF file (multipart/form-data)"),
) -> UserProfile:
    """
    Upload a CV PDF, extract structured data, and update the user's profile.

    Accepts multipart/form-data (field name: `file`) or a raw binary body
    with Content-Type: application/pdf.
    """
    content_type = request.headers.get("content-type", "")

    if file is not None:
        if file.content_type not in _PDF_CONTENT_TYPES:
            raise HTTPException(
                status_code=422,
                detail=f"Only PDF files are accepted. Got: {file.content_type!r}",
            )
        filename = file.filename or "cv.pdf"
        try:
            pdf_bytes = await file.read()
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Could not read file: {exc}") from exc
    elif any(ct in content_type for ct in ("application/pdf", "octet-stream", "binary")):
        filename = "cv.pdf"
        try:
            pdf_bytes = await request.body()
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Could not read body: {exc}") from exc
    else:
        raise HTTPException(
            status_code=422,
            detail="Send the PDF as multipart/form-data (field: 'file') or raw binary body.",
        )

    if not pdf_bytes:
        raise HTTPException(status_code=422, detail="Uploaded file is empty.")

    if not filename.lower().endswith(".pdf"):
        filename = "cv.pdf"

    # Upload to Storage
    storage_path = f"{user_id}/{filename}"
    try:
        upload_cv_pdf(storage_path, pdf_bytes)
    except Exception as exc:
        logger.exception("Storage upload failed for user_id=%s", user_id)
        raise HTTPException(status_code=502, detail=f"Storage upload error: {exc}") from exc

    # Extract text
    try:
        result = extract_text_from_pdf(pdf_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("PDF extraction failed for user_id=%s", user_id)
        raise HTTPException(status_code=500, detail=f"Extraction error: {exc}") from exc

    # Parse with MiniMax
    try:
        structured_dict = parse_cv_with_minimax(result.text)
    except RuntimeError as exc:
        logger.exception("MiniMax call failed for user_id=%s", user_id)
        raise HTTPException(status_code=502, detail=f"MiniMax error: {exc}") from exc

    cv = StructuredCV.model_validate(structured_dict)

    # Upsert cv_data row
    settings = get_settings()
    client = get_supabase()
    try:
        client.table("cv_data").upsert(
            {
                "user_id": str(user_id),
                "storage_path": storage_path,
                "structured_json": structured_dict,
                "model_used": settings.anthropic_model,
            },
            on_conflict="user_id",
        ).execute()
    except Exception:
        logger.exception("Failed to upsert cv_data for user_id=%s", user_id)

    # Build updated profile from parsed CV and merge with existing
    current = _fetch_profile(user_id)

    # Collapse experience list into a summary string
    exp_summary = current.experience
    if cv.experience:
        lines = []
        for exp in cv.experience:
            period = ""
            if exp.start_date:
                period = f"{exp.start_date}–{exp.end_date or 'present'}"
            lines.append(f"{exp.title} at {exp.company}" + (f" ({period})" if period else ""))
        exp_summary = "\n".join(lines)

    updated = UserProfile(
        name=cv.name or current.name,
        role=current.role,
        skills=cv.skills if cv.skills else current.skills,
        experience=exp_summary,
        projects=current.projects,
        references=current.references,
    )

    try:
        _upsert_profile(user_id, updated)
    except Exception as exc:
        logger.exception("Failed to update profile after CV parse for user_id=%s", user_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return updated
