from __future__ import annotations

import re
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from features.measurements.dependencies import get_measurement_service
from features.measurements.schemas import Measurement, MeasurementType
from features.measurements.schemas.measurement_list_response import (
    MeasurementLink,
    MeasurementListResponse,
)
from features.measurements.schemas.measurement_registry import (
    resolve_measurement_type,
)
from features.measurements.service import MeasurementService

router = APIRouter(prefix="/subjects", tags=["measurements"])
_INTEGER_QUERY_PATTERN = re.compile(r"[+-]?[0-9]+\Z")


def _parse_pagination_value(name: str, value: str) -> int:
    if _INTEGER_QUERY_PATTERN.fullmatch(value) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{name} must be an integer.",
        )

    try:
        parsed = int(value)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{name} must be an integer.",
        ) from None
    if parsed < (1 if name == "limit" else 0):
        requirement = (
            "a positive integer" if name == "limit" else "a non-negative integer"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{name} must be {requirement}.",
        )
    return parsed


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
    response: Response,
) -> MeasurementListResponse:
    items, total, effective_limit = measurement_service.list(
        subject_id, measurement_type, limit, offset
    )

    def make_link(rel: str, link_offset: int) -> MeasurementLink:
        query_params = []
        if measurement_type is not None:
            query_params.append(("type", measurement_type))
        query_params.extend(
            (("limit", str(effective_limit)), ("offset", str(link_offset)))
        )
        query = urlencode(query_params)
        return MeasurementLink(href=f"{path}?{query}", rel=rel)

    previous_link = (
        make_link("prev", max(offset - effective_limit, 0)) if offset > 0 else None
    )
    next_offset = offset + effective_limit
    next_link = make_link("next", next_offset) if next_offset < total else None
    last_offset = max((total - 1) // effective_limit, 0) * effective_limit
    first_link = make_link("first", 0)
    last_link = make_link("last", last_offset)

    response.status_code = (
        status.HTTP_206_PARTIAL_CONTENT
        if total > effective_limit
        else status.HTTP_200_OK
    )
    response.headers["X-Count"] = str(len(items))
    response.headers["X-Total-Count"] = str(total)
    header_links = [
        f'<{link.href}>; rel="{link.rel}"'
        for link in (previous_link, next_link)
        if link is not None
    ]
    if header_links:
        response.headers["Link"] = ", ".join(header_links)

    return MeasurementListResponse(
        items=items,
        total=total,
        links={
            "prev": previous_link,
            "next": next_link,
            "first": first_link,
            "last": last_link,
        },
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
    response: Response,
    type: Annotated[
        str | None, Query(description="Filter measurements by type")
    ] = None,
    limit: Annotated[
        str | None,
        Query(description="Maximum number of measurements to return"),
    ] = None,
    offset: Annotated[
        str | None, Query(description="Number of measurements to skip")
    ] = None,
) -> MeasurementListResponse:
    """List a subject's measurements using the legacy collection path."""

    parsed_limit = (
        _parse_pagination_value("limit", limit) if limit is not None else None
    )
    parsed_offset = (
        _parse_pagination_value("offset", offset) if offset is not None else 0
    )
    return _list_measurements(
        subject_id,
        f"/subjects/{subject_id}/measurements",
        type,
        parsed_limit,
        parsed_offset,
        measurement_service,
        response,
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
    response: Response,
    limit: Annotated[
        str | None,
        Query(description="Maximum number of measurements to return"),
    ] = None,
    offset: Annotated[
        str | None, Query(description="Number of measurements to skip")
    ] = None,
) -> MeasurementListResponse:
    """List measurements by canonical type or plural resource name."""
    resolved_type = resolve_measurement_type(measurement_type)
    if resolved_type is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Unsupported measurement type '{measurement_type}'",
        )

    parsed_limit = (
        _parse_pagination_value("limit", limit) if limit is not None else None
    )
    parsed_offset = (
        _parse_pagination_value("offset", offset) if offset is not None else 0
    )
    return _list_measurements(
        subject_id,
        f"/subjects/{subject_id}/{measurement_type}",
        resolved_type.value,
        parsed_limit,
        parsed_offset,
        measurement_service,
        response,
    )
