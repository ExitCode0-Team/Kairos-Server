"""
CV parsing via MiniMax's Anthropic-compatible endpoint.

MiniMax exposes the Anthropic Messages API at a custom base_url, so we
use the official `anthropic` SDK and just point it at MiniMax's server.

Env vars required:
  ANTHROPIC_API_KEY   — your MiniMax API key
  ANTHROPIC_BASE_URL  — https://api.minimax.io/anthropic
  ANTHROPIC_MODEL     — MiniMax-Text-01  (or whichever model you have access to)
"""
from __future__ import annotations

import json
import logging
import re

import anthropic

from app.config import get_settings

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are an expert CV/resume parser. Extract every piece of information from the
provided CV text and return ONLY a valid JSON object — no markdown fences,
no explanation, no extra keys outside the schema below.

Required JSON structure:
{
  "name": "Full Name",
  "email": "email@example.com or null",
  "phone": "phone number or null",
  "location": "City, Country or null",
  "summary": "professional summary paragraph or null",
  "skills": ["skill1", "skill2"],
  "experience": [
    {
      "company": "Company Name",
      "title": "Job Title",
      "start_date": "YYYY-MM or YYYY",
      "end_date": "YYYY-MM or YYYY or null when current role",
      "current": false,
      "description": "responsibilities / achievements as a string"
    }
  ],
  "education": [
    {
      "institution": "University / School Name",
      "degree": "BSc / MSc / PhD / etc.",
      "field": "Field of Study or null",
      "start_date": "YYYY or null",
      "end_date": "YYYY or null",
      "gpa": "GPA string or null"
    }
  ],
  "certifications": ["Certification Name 1"],
  "languages": ["English", "French"],
  "links": {
    "linkedin": "URL or null",
    "github": "URL or null",
    "portfolio": "URL or null"
  }
}

Rules:
- Use null (JSON null, not the string "null") for missing fields.
- All dates as strings. If only a year is available, use "YYYY".
- skills must be a flat list of short strings.
- Return nothing except the JSON object.
"""


def parse_cv_with_minimax(raw_text: str) -> dict:
    """
    Send extracted CV text to MiniMax (via Anthropic SDK) and return a structured dict.

    Raises RuntimeError on API or parsing failure.
    """
    settings = get_settings()

    client = anthropic.Anthropic(
        api_key=settings.anthropic_api_key,
        base_url=settings.anthropic_base_url,
    )

    logger.info(
        "Calling MiniMax via Anthropic SDK — base_url=%s model=%s",
        settings.anthropic_base_url,
        settings.anthropic_model,
    )

    try:
        message = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=4096,
            system=_SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": f"Parse this CV:\n\n{raw_text}"},
            ],
            temperature=0.1,
        )
    except anthropic.APIStatusError as exc:
        raise RuntimeError(
            f"MiniMax API error {exc.status_code}: {exc.message}"
        ) from exc
    except anthropic.APIConnectionError as exc:
        raise RuntimeError(f"MiniMax connection failed: {exc}") from exc

    raw_content = _extract_text(message)
    return _parse_json(raw_content)


def _extract_text(message) -> str:
    """
    Pull the assistant's text reply out of a Messages API response.

    MiniMax-M2.x thinking models emit a `ThinkingBlock` before the `TextBlock`,
    so we can't blindly read `content[0].text`. Iterate and concatenate all
    `text` blocks.
    """
    parts: list[str] = []
    for block in message.content:
        if getattr(block, "type", None) == "text":
            parts.append(block.text)
        elif hasattr(block, "text"):
            parts.append(block.text)

    if not parts:
        raise RuntimeError(
            f"No text block in model response. Blocks: "
            f"{[getattr(b, 'type', type(b).__name__) for b in message.content]}"
        )

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_json(content: str) -> dict:
    """Extract JSON from the model reply, handling accidental markdown fences."""
    stripped = content.strip()

    fence = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", stripped)
    if fence:
        stripped = fence.group(1).strip()

    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Model response is not valid JSON: {exc}\n\nContent: {content[:500]}"
        ) from exc

    if not isinstance(parsed, dict):
        raise RuntimeError(f"Expected a JSON object, got {type(parsed).__name__}")

    return parsed
