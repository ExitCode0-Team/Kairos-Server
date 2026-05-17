"""Liveness endpoint."""

from fastapi import APIRouter

from app.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/v1/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness check — used by Railway / load balancers."""
    return HealthResponse()
