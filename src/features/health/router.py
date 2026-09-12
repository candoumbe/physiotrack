from datetime import UTC, datetime

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    """Gives the health status of the API."""
    return {
        "status": "ok",
        "timestamp": datetime.now(UTC).isoformat(),
    }
