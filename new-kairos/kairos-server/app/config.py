"""
Settings loaded from .env (copy .env.example → .env and fill in values).
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Supabase
    supabase_url: str
    supabase_service_key: str
    cv_uploads_bucket: str = "cv-uploads"

    # MiniMax via Anthropic-compatible endpoint
    anthropic_api_key: str
    anthropic_base_url: str = "https://api.minimax.io/anthropic"
    anthropic_model: str = "MiniMax-M2.7"

    # Supabase JWT secret — used to verify access tokens from the frontend
    # Found at: Project Settings → API → JWT Settings → JWT Secret
    supabase_jwt_secret: str = ""

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # PDF extraction tuning
    min_text_chars: int = 40   # below this → fall back to OCR
    ocr_dpi: int = 200


@lru_cache
def get_settings() -> Settings:
    return Settings()
