"""
CV PDF text extraction.

Strategy (same idea as the Edge extract-cv function, but with stronger OCR here):

  1. Try PyMuPDF — fast, works when the PDF has a real text layer.
  2. If text is missing or too short, rasterize pages and run Tesseract OCR.

System dependencies for OCR (install on the host / Docker image):
  - tesseract-ocr
  - poppler-utils  (used by pdf2image)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

import fitz  # PyMuPDF
import pytesseract
from pdf2image import convert_from_bytes
from PIL import Image

from app.config import get_settings

logger = logging.getLogger(__name__)

ExtractMethod = Literal["pymupdf", "ocr"]


@dataclass(frozen=True)
class ExtractResult:
    """Outcome of reading a PDF."""

    text: str
    method: ExtractMethod


def extract_text_from_pdf(pdf_bytes: bytes) -> ExtractResult:
    """
    Extract plain text from PDF bytes.

    Raises ValueError if both strategies yield insufficient text.
  """
    settings = get_settings()

    native_text = _extract_with_pymupdf(pdf_bytes)
    if len(native_text.strip()) >= settings.min_text_chars:
        logger.info("Extracted %d chars via PyMuPDF", len(native_text))
        return ExtractResult(text=native_text.strip(), method="pymupdf")

    logger.info(
        "PyMuPDF returned %d chars (< %d) — falling back to OCR",
        len(native_text.strip()),
        settings.min_text_chars,
    )
    ocr_text = _extract_with_ocr(pdf_bytes)
    combined = (native_text + "\n" + ocr_text).strip() if native_text.strip() else ocr_text.strip()

    if len(combined) < settings.min_text_chars:
        raise ValueError(
            "Could not extract enough text from PDF. "
            "The file may be blank, encrypted, or OCR dependencies may be missing."
        )

    return ExtractResult(text=combined, method="ocr")


def _extract_with_pymupdf(pdf_bytes: bytes) -> str:
    """Read embedded text from each page."""
    parts: list[str] = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page in doc:
            parts.append(page.get_text("text"))
    return "\n".join(parts)


def _extract_with_ocr(pdf_bytes: bytes) -> str:
    """
    Render each page to an image and run Tesseract.

    Requires: tesseract binary on PATH, poppler for pdf2image.
    """
    settings = get_settings()
    images: list[Image.Image] = convert_from_bytes(pdf_bytes, dpi=settings.ocr_dpi)

    page_texts: list[str] = []
    for index, image in enumerate(images, start=1):
        logger.debug("OCR page %d/%d", index, len(images))
        page_texts.append(pytesseract.image_to_string(image))

    return "\n\n".join(page_texts)
