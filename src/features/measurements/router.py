from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from features.measurements.dependencies import get_measurement_service
from features.measurements.schemas import Measurement, MeasurementType
from features.measurements.schemas.measurement_list_response import (
    MeasurementListResponse,
)
from features.measurements.schemas.measurement_registry import (
    resolve_measurement_type,
)
from features.measurements.service import MeasurementService

router = APIRouter(prefix="/subjects", tags=["measurements"])


def _create_measurement(
    subject_id: str,
    measurement: Measurement,
    response: Response,
    measurement_service: MeasurementService,
    measurement_type: MeasurementType | None = None,
) -> Measurement:
    if measurement_type is not None and measurement.type != measurement_type:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"Measurement type '{measurement.type.value}' does not match "
                f"URL type '{measurement_type.value}'"
            ),
        )

    created = measurement_service.create(subject_id, measurement)
    response.headers["Location"] = f"/subjects/{subject_id}/measurements/{created.id}"
    return created


@router.post(
    "/{subject_id}/measurements",
    status_code=status.HTTP_201_CREATED,
    response_model=Measurement,
)
def create_measurement(
    subject_id: str,
    measurement: Measurement,
    response: Response,
    measurement_service: Annotated[
        MeasurementService, Depends(get_measurement_service)
    ],
) -> Measurement:
    """Create a measurement for a subject using the legacy collection path."""
    return _create_measurement(subject_id, measurement, response, measurement_service)


@router.post(
    "/{subject_id}/{measurement_type}",
    status_code=status.HTTP_201_CREATED,
    response_model=Measurement,
)
@router.post(
    "/{subject_id}/measurements/{measurement_type}",
    status_code=status.HTTP_201_CREATED,
    response_model=Measurement,
)
def create_typed_measurement(
    subject_id: str,
    measurement_type: str,
    measurement: Measurement,
    response: Response,
    measurement_service: Annotated[
        MeasurementService, Depends(get_measurement_service)
    ],
) -> Measurement:
    """Create a measurement whose type is stated in the URL."""
    resolved_type = resolve_measurement_type(measurement_type)
    if resolved_type is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Unsupported measurement type '{measurement_type}'",
        )
    return _create_measurement(
        subject_id, measurement, response, measurement_service, resolved_type
    )


@router.get(
    "/{subject_id}/measurements/{measurement_id}",
    response_model=Measurement,
)
def get_measurement(
    subject_id: str,
    measurement_id: str,
    measurement_service: Annotated[
        MeasurementService, Depends(get_measurement_service)
    ],
) -> Measurement:
    """Retrieve a subject's measurement by id."""
    measurement = measurement_service.get(subject_id, measurement_id)
    if measurement is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Measurement not found"
        )
    return measurement


def _list_measurements(
    subject_id: str,
    path: str,
    measurement_type: str | None,
    limit: int | None,
    offset: int,
    measurement_service: MeasurementService,
) -> MeasurementListResponse:
    items, total, effective_limit = measurement_service.list(
        subject_id, measurement_type, limit, offset
    )

    next_offset = offset + effective_limit
    previous_offset = max(offset - effective_limit, 0)
    query_params: list[str] = []
    if measurement_type is not None:
        query_params.append(f"type={measurement_type}")
    query_params.append(f"limit={effective_limit}")

    next_url = None
    previous_url = None
    if next_offset < total:
        next_url = f"{path}?{'&'.join([*query_params, f'offset={next_offset}'])}"
    if offset > 0:
        previous_url = (
            f"{path}?{'&'.join([*query_params, f'offset={previous_offset}'])}"
        )

    return MeasurementListResponse(
        items=items,
        pagination={
            "total": total,
            "limit": effective_limit,
            "offset": offset,
        },
        links={"next": next_url, "previous": previous_url},
    )


@router.get(
    "/{subject_id}/measurements",
    response_model=MeasurementListResponse,
)
def list_measurements(
    subject_id: str,
    measurement_service: Annotated[
        MeasurementService, Depends(get_measurement_service)
    ],
    type: Annotated[
        str | None, Query(description="Filter measurements by type")
    ] = None,
    limit: Annotated[
        int | None, Query(description="Maximum number of measurements to return", ge=1)
    ] = None,
    offset: Annotated[
        int, Query(description="Number of measurements to skip", ge=0)
    ] = 0,
) -> MeasurementListResponse:
    """List a subject's measurements using the legacy collection path."""
    return _list_measurements(
        subject_id,
        f"/subjects/{subject_id}/measurements",
        type,
        limit,
        offset,
        measurement_service,
    )


@router.get(
    "/{subject_id}/{measurement_type}",
    response_model=MeasurementListResponse,
)
def list_measurements_by_type(
    subject_id: str,
    measurement_type: str,
    measurement_service: Annotated[
        MeasurementService, Depends(get_measurement_service)
    ],
    limit: Annotated[
        int | None, Query(description="Maximum number of measurements to return", ge=1)
    ] = None,
    offset: Annotated[
        int, Query(description="Number of measurements to skip", ge=0)
    ] = 0,
) -> MeasurementListResponse:
    """List measurements by canonical type or plural resource name."""
    resolved_type = resolve_measurement_type(measurement_type)
    if resolved_type is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Unsupported measurement type '{measurement_type}'",
        )

    return _list_measurements(
        subject_id,
        f"/subjects/{subject_id}/{measurement_type}",
        resolved_type.value,
        limit,
        offset,
        measurement_service,
    )
