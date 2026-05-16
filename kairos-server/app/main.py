"""
Kairos Server — FastAPI entrypoint.

Run locally:
  uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import cv, extract, health, projects

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

app = FastAPI(
    title="Kairos Server",
    description="CV extraction and parsing API — powered by MiniMax",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(extract.router)
app.include_router(cv.router)
app.include_router(projects.router)


@app.get("/")
def root() -> dict[str, str]:
    return {"service": "kairos-server", "docs": "/docs", "health": "/health"}


def run() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=True)


if __name__ == "__main__":
    run()
