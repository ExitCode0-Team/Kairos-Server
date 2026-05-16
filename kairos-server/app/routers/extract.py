"""
POST /api/v1/extract

Pipeline:
  1. Download PDF from Supabase Storage (cv-uploads bucket).
  2. Extract text — PyMuPDF first, Tesseract OCR fallback.
  3. Send text to MiniMax → get structured CV JSON.
  4. Upsert into public.cv_data (one row per user, overwritten on re-upload).
  5. Return the structured CV.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.config import get_settings
from app.deps import verify_api_secret
from app.schemas import ExtractRequest, ExtractResponse, StructuredCV
from app.services.extraction import extract_text_from_pdf
from app.services.minimax import parse_cv_with_minimax
from app.services.storage import download_cv_pdf
from app.supabase_client import get_supabase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["extract"])


@router.post(
    "/extract",
    response_model=ExtractResponse,
    dependencies=[Depends(verify_api_secret)],
    summary="Extract and parse a CV from Supabase Storage",
)
def extract_cv(body: ExtractRequest) -> ExtractResponse:
    """
    Full CV pipeline triggered from Postman or any HTTP client.

    ```json
    {
      "user_id": "your-supabase-user-uuid",
      "storage_path": "your-supabase-user-uuid/my-cv.pdf"
    }
    ```

    The `storage_path` is the path **inside** the `cv-uploads` bucket.
    It must start with `{user_id}/` (enforced by Storage RLS when uploading
    as an authenticated user; the server uses service_role so it can read any path).
    """
    # 1. Download -----------------------------------------------------------------
    try:
        pdf_bytes = download_cv_pdf(str(body.storage_path))
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Storage download failed")
        raise HTTPException(status_code=502, detail=f"Storage error: {exc}") from exc

    # 2. Extract text -------------------------------------------------------------
    try:
        result = extract_text_from_pdf(pdf_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("PDF extraction failed")
        raise HTTPException(status_code=500, detail=f"Extraction error: {exc}") from exc

    # 3. Parse with MiniMax -------------------------------------------------------
    try:
        structured_dict = parse_cv_with_minimax(result.text)
    except RuntimeError as exc:
        logger.exception("MiniMax call failed")
        raise HTTPException(status_code=502, detail=f"MiniMax error: {exc}") from exc

    cv = StructuredCV.model_validate(structured_dict)

    # 4. Store in cv_data (upsert — one row per user) -----------------------------
    _upsert_cv_data(
        user_id=str(body.user_id),
        storage_path=body.storage_path,
        structured_dict=structured_dict,
    )

    return ExtractResponse(
        user_id=body.user_id,
        storage_path=body.storage_path,
        extract_method=result.method,
        char_count=len(result.text),
        cv=cv,
    )


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------


def _upsert_cv_data(user_id: str, storage_path: str, structured_dict: dict) -> None:
    settings = get_settings()
    client = get_supabase()
    try:
        client.table("cv_data").upsert(
            {
                "user_id": user_id,
                "storage_path": storage_path,
                "structured_json": structured_dict,
                "model_used": settings.anthropic_model,
            },
            on_conflict="user_id",
        ).execute()
        logger.info("Upserted cv_data for user_id=%s", user_id)
    except Exception:
        logger.exception("Failed to upsert cv_data for user_id=%s", user_id)
