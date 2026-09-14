from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from features.measurements.schemas import Measurement

router = APIRouter(prefix="/subjects", tags=["measurements"])

_store: dict[str, list[Measurement]] = {}


def _ensure_subject(subject_id: str) -> list[Measurement]:
    return _store.setdefault(subject_id, [])


@router.post("/{subject_id}/measurements", status_code=status.HTTP_201_CREATED)
def create_measurement(subject_id: str, measurement: Measurement) -> Measurement:

    measurements = _ensure_subject(subject_id)
    clone = measurement.model_copy(update={"subject_id": subject_id})
    measurements.append(clone)
    return clone


@router.get("/{subject_id}/measurements")
def list_measurements(
    subject_id: str,
    type: Annotated[str | None, Query(description="Filter measurements by type")] = None,
    limit: Annotated[int | None, Query(description="Maximum number of measurements to return", ge=1)] = None,
    offset: Annotated[int, Query(description="Number of measurements to skip", ge=0)] = 0,
) -> dict[str, object]:
    measurements = _store.get(subject_id, [])
    if type is not None:
        measurements = [m for m in measurements if m.type.value == type]

    total = len(measurements)
    effective_limit = total if limit is None else limit
    paginated = measurements[offset : offset + effective_limit]

    next_offset = offset + effective_limit
    previous_offset = max(offset - effective_limit, 0)

    params: list[str] = []
    if type is not None:
        params.append(f"type={type}")

    params.extend([f"limit={effective_limit}", f"offset={{}}".format(next_offset)])

    next_url = None
    previous_url = None

    if next_offset < total:
        next_query = "&".join([*params[:-1], f"offset={next_offset}"])
        next_url = f"/subjects/{subject_id}/measurements?{next_query}"

    if offset > 0:
        previous_query = "&".join([*params[:-1], f"offset={previous_offset}"])
        previous_url = f"/subjects/{subject_id}/measurements?{previous_query}"

    return {
        "items": paginated,
        "pagination": {
            "total": total,
            "limit": effective_limit,
            "offset": offset,
        },
        "links": {
            "next": next_url,
            "previous": previous_url,
        },
    }
