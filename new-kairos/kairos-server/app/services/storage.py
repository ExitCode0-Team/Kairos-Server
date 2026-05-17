"""Supabase Storage helpers — download and upload CV PDFs."""

from __future__ import annotations

from app.config import get_settings
from app.supabase_client import get_supabase


def download_cv_pdf(storage_path: str) -> bytes:
    """
    Fetch raw PDF bytes from the cv-uploads bucket.

    storage_path — path inside the bucket, e.g. "{user_id}/my-cv.pdf"

    Raises RuntimeError if the object does not exist or the download fails.
    """
    settings = get_settings()
    client = get_supabase()

    response = client.storage.from_(settings.cv_uploads_bucket).download(storage_path)

    if not response:
        raise RuntimeError(f"Empty response for path: {storage_path!r}")

    if isinstance(response, bytes):
        return response

    raise RuntimeError(f"Unexpected download response type: {type(response)}")


def upload_cv_pdf(storage_path: str, pdf_bytes: bytes) -> str:
    """
    Upload raw PDF bytes to the cv-uploads bucket.

    storage_path — destination inside the bucket, e.g. "{user_id}/my-cv.pdf"

    Uses upsert=True so re-uploading the same filename overwrites the previous file.
    Returns storage_path on success.
    Raises RuntimeError on failure.
    """
    settings = get_settings()
    client = get_supabase()

    client.storage.from_(settings.cv_uploads_bucket).upload(
        path=storage_path,
        file=pdf_bytes,
        file_options={"content-type": "application/pdf", "upsert": "true"},
    )

    return storage_path
