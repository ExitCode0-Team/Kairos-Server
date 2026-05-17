"""
CV file management endpoints.

GET    /v1/cvs              — list the user's uploaded CV files
POST   /v1/cvs              — upload a new CV PDF (stores file + parses it)
DELETE /v1/cvs/{id}         — delete a CV file
POST   /v1/cvs/{id}/set-default — mark a CV as the default
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile

from app.config import get_settings
from app.deps import get_current_user
from app.schemas import Cv, CvListResponse, StructuredCV
from app.services.extraction import extract_text_from_pdf
from app.services.minimax import parse_cv_with_minimax
from app.services.storage import upload_cv_pdf
from app.supabase_client import get_supabase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/cvs", tags=["cvs"])

_PDF_CONTENT_TYPES = {"application/pdf", "application/octet-stream", "binary/octet-stream"}


def _row_to_cv(row: dict) -> Cv:
    return Cv(
        id=UUID(row["id"]),
        name=row["name"],
        uploadedAt=row["uploaded_at"],
        isDefault=row["is_default"],
        sizeBytes=row.get("size_bytes") or 0,
    )


# ---------------------------------------------------------------------------
# GET /v1/cvs
# ---------------------------------------------------------------------------

@router.get("", response_model=CvListResponse)
def list_cvs(user_id: UUID = Depends(get_current_user)) -> CvListResponse:
    """Return all uploaded CV files for the authenticated user."""
    client = get_supabase()
    resp = (
        client.table("cvs")
        .select("id, name, storage_path, size_bytes, is_default, uploaded_at")
        .eq("user_id", str(user_id))
        .order("uploaded_at", desc=True)
        .execute()
    )
    return CvListResponse(items=[_row_to_cv(row) for row in (resp.data or [])])


# ---------------------------------------------------------------------------
# POST /v1/cvs
# ---------------------------------------------------------------------------

@router.post("", response_model=Cv, status_code=201)
async def upload_cv(
    request: Request,
    user_id: UUID = Depends(get_current_user),
    file: UploadFile = File(default=None, description="PDF file (multipart/form-data)"),
) -> Cv:
    """
    Upload a new CV PDF. The file is stored in Supabase Storage, parsed by
    MiniMax, and a `cvs` row is created. The first upload is automatically
    set as the default.
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

    # Parse (best-effort — don't fail the upload if parsing errors)
    structured_dict: dict = {}
    try:
        result = extract_text_from_pdf(pdf_bytes)
        structured_dict = parse_cv_with_minimax(result.text)
    except Exception:
        logger.warning("CV parsing failed for user_id=%s; storing file without parsed data", user_id)

    # Determine if this is the first CV (auto-set as default)
    client = get_supabase()
    existing = client.table("cvs").select("id", count="exact").eq("user_id", str(user_id)).execute()
    is_first = (existing.count or 0) == 0

    # Insert cvs row
    try:
        settings = get_settings()
        cv_resp = (
            client.table("cvs")
            .insert(
                {
                    "user_id": str(user_id),
                    "name": filename,
                    "storage_path": storage_path,
                    "size_bytes": len(pdf_bytes),
                    "is_default": is_first,
                }
            )
            .execute()
        )
        cv_row = cv_resp.data[0]
    except Exception as exc:
        logger.exception("Failed to insert cvs row for user_id=%s", user_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    # Also upsert cv_data for profile CV usage
    if structured_dict:
        try:
            settings = get_settings()
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
            logger.warning("Failed to upsert cv_data for user_id=%s", user_id)

    # Log activity
    try:
        client.table("activities").insert(
            {"user_id": str(user_id), "icon_key": "cv", "label": f"Uploaded CV: {filename}"}
        ).execute()
    except Exception:
        pass

    return _row_to_cv(cv_row)


# ---------------------------------------------------------------------------
# DELETE /v1/cvs/{id}
# ---------------------------------------------------------------------------

@router.delete("/{cv_id}", status_code=200)
def delete_cv(
    cv_id: UUID,
    user_id: UUID = Depends(get_current_user),
) -> dict:
    """Delete a CV file. Returns { ok: true }."""
    client = get_supabase()

    # Verify ownership
    existing = (
        client.table("cvs")
        .select("id, is_default, storage_path")
        .eq("id", str(cv_id))
        .eq("user_id", str(user_id))
        .limit(1)
        .execute()
    )
    if not existing.data:
        raise HTTPException(status_code=404, detail="CV not found.")

    row = existing.data[0]
    try:
        client.table("cvs").delete().eq("id", str(cv_id)).execute()
    except Exception as exc:
        logger.exception("Failed to delete cv %s for user %s", cv_id, user_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    # If we deleted the default, promote the newest remaining one
    if row["is_default"]:
        try:
            remaining = (
                client.table("cvs")
                .select("id")
                .eq("user_id", str(user_id))
                .order("uploaded_at", desc=True)
                .limit(1)
                .execute()
            )
            if remaining.data:
                client.table("cvs").update({"is_default": True}).eq(
                    "id", remaining.data[0]["id"]
                ).execute()
        except Exception:
            logger.warning("Failed to promote next default CV for user %s", user_id)

    return {"ok": True}


# ---------------------------------------------------------------------------
# POST /v1/cvs/{id}/set-default
# ---------------------------------------------------------------------------

@router.post("/{cv_id}/set-default", response_model=Cv)
def set_default_cv(
    cv_id: UUID,
    user_id: UUID = Depends(get_current_user),
) -> Cv:
    """Mark a CV as the default, clearing the flag from all others."""
    client = get_supabase()

    # Verify ownership
    existing = (
        client.table("cvs")
        .select("id, name, storage_path, size_bytes, is_default, uploaded_at")
        .eq("id", str(cv_id))
        .eq("user_id", str(user_id))
        .limit(1)
        .execute()
    )
    if not existing.data:
        raise HTTPException(status_code=404, detail="CV not found.")

    try:
        # Clear all defaults for this user, then set the requested one
        client.table("cvs").update({"is_default": False}).eq("user_id", str(user_id)).execute()
        client.table("cvs").update({"is_default": True}).eq("id", str(cv_id)).execute()
    except Exception as exc:
        logger.exception("Failed to set default CV %s for user %s", cv_id, user_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    updated = (
        client.table("cvs")
        .select("id, name, storage_path, size_bytes, is_default, uploaded_at")
        .eq("id", str(cv_id))
        .limit(1)
        .execute()
    )
    return _row_to_cv(updated.data[0])
