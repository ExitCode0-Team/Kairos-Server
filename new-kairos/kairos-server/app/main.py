"""
Kairos Server — FastAPI entrypoint.

Run locally:
  uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"""

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.routers import (
    connectors,
    cvs,
    dashboard,
    health,
    matches,
    preferences,
    profile,
    settings,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

app = FastAPI(
    title="Kairos Server",
    description="Job matching and CV management API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Validation error → unified { error, fieldErrors } shape
# ---------------------------------------------------------------------------

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    field_errors: dict[str, list[str]] = {}
    for err in exc.errors():
        loc = ".".join(str(x) for x in err["loc"] if x != "body")
        field_errors.setdefault(loc, []).append(err["msg"])
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": "Validation failed", "fieldErrors": field_errors},
    )


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(health.router)
app.include_router(profile.router)
app.include_router(matches.router)
app.include_router(connectors.router)
app.include_router(dashboard.router)
app.include_router(cvs.router)
app.include_router(settings.router)
app.include_router(preferences.router)


@app.get("/")
def root() -> dict[str, str]:
    return {"service": "kairos-server", "docs": "/docs", "health": "/v1/health"}


def run() -> None:
    import uvicorn

    s = get_settings()
    uvicorn.run("app.main:app", host=s.host, port=s.port, reload=True)


if __name__ == "__main__":
    run()
