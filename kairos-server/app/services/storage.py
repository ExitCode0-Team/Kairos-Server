"""Download CV PDFs from Supabase Storage."""

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
