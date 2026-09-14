from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status

from features.measurements.schemas import Measurement

router = APIRouter(prefix="/subjects", tags=["measurements"])

_store: dict[str, list[Measurement]] = {}


def _ensure_subject(subject_id: str) -> list[Measurement]:
    return _store.setdefault(subject_id, [])


@router.post("/{subject_id}/measurements", status_code=status.HTTP_201_CREATED)
def create_measurement(
    subject_id: str, measurement: Measurement, response: Response
) -> Measurement:
    """
    Create a new measurement for the specified subject.

    Args:
        subject_id (str): The ID of the subject.
        measurement (Measurement): The measurement data to create.

    Returns:
        Measurement: The created measurement with the subject ID included.
    """

    measurements = _ensure_subject(subject_id)
    clone = measurement.model_copy(update={"subject_id": subject_id})
    measurements.append(clone)

    response.headers["Location"] = f"/subjects/{subject_id}/measurements/{clone.id}"
    response.status_code = status.HTTP_201_CREATED

    return clone


@router.get("/{subject_id}/measurements/{measurement_id}")
def get_measurement(subject_id: str, measurement_id: str) -> Measurement:
    """
    Retrieve a specific measurement for the specified subject.

    Args:
        subject_id (str): The ID of the subject.
        measurement_id (str): The ID of the measurement to retrieve.

    Returns:
        Measurement: The requested measurement.

    Raises:
        HTTPException: If the measurement is not found.
    """
    measurements = _store.get(subject_id)
    if measurements is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Measurement not found"
        )

    for m in measurements:
        if m.id == measurement_id:
            return m
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="Measurement not found"
    )


@router.get("/{subject_id}/measurements")
def list_measurements(
    subject_id: str,
    type: Annotated[
        str | None, Query(description="Filter measurements by type")
    ] = None,
    limit: Annotated[
        int | None, Query(description="Maximum number of measurements to return", ge=1)
    ] = None,
    offset: Annotated[
        int, Query(description="Number of measurements to skip", ge=0)
    ] = 0,
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

    params.extend([f"limit={effective_limit}", f"offset={next_offset}"])

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
