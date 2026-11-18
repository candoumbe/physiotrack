from __future__ import annotations

from typing import Annotated
from urllib.parse import quote, urlencode
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from features.measurements.dependencies import get_measurement_service
from features.measurements.schemas import (
    MEASUREMENT_MODELS,
    Measurement,
    MeasurementBase,
    MeasurementType,
)
from features.measurements.schemas.measurement_list_response import (
    MeasurementLink,
    MeasurementListResponse,
)
from features.measurements.schemas.measurement_registry import plural_resource_name
from features.measurements.service import MeasurementAdapter, MeasurementService

router = APIRouter(prefix="/subjects", tags=["measurements"])


def _create_measurement(
    subject_id: UUID,
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
    resource_name = plural_resource_name(created.type)
    response.headers["Location"] = (
        f"/subjects/{quote(str(subject_id), safe='')}/{resource_name}/{created.id}"
    )
    return created


@router.post(
    "/{subject_id}/measurements",
    status_code=status.HTTP_201_CREATED,
    response_model=Measurement,
)
def create_measurement(
    subject_id: UUID,
    measurement: Measurement,
    response: Response,
    measurement_service: Annotated[
        MeasurementService, Depends(get_measurement_service)
    ],
) -> Measurement:
    """Create a measurement for a subject using the legacy collection path."""
    return _create_measurement(subject_id, measurement, response, measurement_service)


def _list_measurements(
    subject_id: UUID,
    path: str,
    measurement_type: str | None,
    limit: int | None,
    offset: int,
    measurement_service: MeasurementService,
    response: Response,
    item_model: type[MeasurementBase] | None = None,
) -> MeasurementListResponse[Measurement]:
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

    if item_model is None:
        response_model = MeasurementListResponse[Measurement]
        response_items = items
    else:
        response_model = MeasurementListResponse[item_model]
        response_items = [
            item_model.model_validate(item.model_dump(exclude={"type"}))
            for item in items
        ]

    return response_model(
        items=response_items,
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
    response_model=MeasurementListResponse[Measurement],
)
def list_measurements(
    subject_id: UUID,
    measurement_service: Annotated[
        MeasurementService, Depends(get_measurement_service)
    ],
    response: Response,
    type: Annotated[
        str | None, Query(description="Filter measurements by type")
    ] = None,
    limit: Annotated[
        int | None,
        Query(ge=1, description="Maximum number of measurements to return"),
    ] = None,
    offset: Annotated[
        int, Query(ge=0, description="Number of measurements to skip")
    ] = 0,
) -> MeasurementListResponse[Measurement]:
    """List a subject's measurements using the legacy collection path."""
    return _list_measurements(
        subject_id,
        f"/subjects/{subject_id}/measurements",
        type,
        limit,
        offset,
        measurement_service,
        response,
    )


def _typed_create_endpoint(
    measurement_type: MeasurementType, model: type[MeasurementBase]
):
    def endpoint(
        subject_id: UUID,
        measurement: MeasurementBase,
        response: Response,
        measurement_service: MeasurementService,
    ) -> MeasurementBase:
        values = measurement.model_dump()
        values["type"] = measurement_type.value
        generic_measurement = MeasurementAdapter.validate_python(values)
        created = _create_measurement(
            subject_id,
            generic_measurement,
            response,
            measurement_service,
            measurement_type,
        )
        return model.model_validate(created.model_dump(exclude={"type"}))

    endpoint.__name__ = f"create_{measurement_type.value}_measurement"
    endpoint.__doc__ = (
        f"Create a {measurement_type.value} measurement without a body discriminator."
    )
    endpoint.__annotations__ = {
        "subject_id": UUID,
        "measurement": model,
        "response": Response,
        "measurement_service": Annotated[
            MeasurementService, Depends(get_measurement_service)
        ],
        "return": model,
    }
    return endpoint


def _typed_list_endpoint(
    measurement_type: MeasurementType, resource_name: str, model: type[MeasurementBase]
):
    def endpoint(
        subject_id: UUID,
        response: Response,
        measurement_service: MeasurementService,
        limit: int | None = None,
        offset: int = 0,
    ) -> MeasurementListResponse[Measurement]:
        return _list_measurements(
            subject_id,
            f"/subjects/{subject_id}/{resource_name}",
            measurement_type.value,
            limit,
            offset,
            measurement_service,
            response,
            model,
        )

    endpoint.__name__ = f"list_{measurement_type.value}_measurements"
    endpoint.__doc__ = f"List {measurement_type.value} measurements."
    endpoint.__annotations__ = {
        "subject_id": UUID,
        "response": Response,
        "measurement_service": Annotated[
            MeasurementService, Depends(get_measurement_service)
        ],
        "limit": Annotated[
            int | None,
            Query(ge=1, description="Maximum number of measurements to return"),
        ],
        "offset": Annotated[
            int, Query(ge=0, description="Number of measurements to skip")
        ],
        "return": MeasurementListResponse[model],
    }
    return endpoint


def _typed_detail_endpoint(
    measurement_type: MeasurementType, model: type[MeasurementBase]
):
    def endpoint(
        subject_id: UUID,
        measure_id: UUID,
        measurement_service: Annotated[
            MeasurementService, Depends(get_measurement_service)
        ],
    ) -> MeasurementBase:
        measurement = measurement_service.get(subject_id, measurement_type, measure_id)
        if measurement is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Measurement not found"
            )
        return model.model_validate(measurement.model_dump(exclude={"type"}))

    endpoint.__name__ = f"get_{measurement_type.value}_measurement"
    endpoint.__doc__ = f"Retrieve a {measurement_type.value} measurement by id."
    return endpoint


for measurement_type, model in MEASUREMENT_MODELS.items():
    resource_names = dict.fromkeys(
        (measurement_type.value, plural_resource_name(measurement_type))
    )
    for resource_name in resource_names:
        router.add_api_route(
            f"/{{subject_id}}/{resource_name}",
            _typed_create_endpoint(measurement_type, model),
            methods=["POST"],
            status_code=status.HTTP_201_CREATED,
            response_model=model,
        )
        router.add_api_route(
            f"/{{subject_id}}/{resource_name}",
            _typed_list_endpoint(measurement_type, resource_name, model),
            methods=["GET"],
            response_model=MeasurementListResponse[model],
        )
        router.add_api_route(
            f"/{{subject_id}}/{resource_name}/{{measure_id}}",
            _typed_detail_endpoint(measurement_type, model),
            methods=["GET"],
            response_model=model,
        )
        router.add_api_route(
            f"/{{subject_id}}/measurements/{resource_name}",
            _typed_create_endpoint(measurement_type, model),
            methods=["POST"],
            status_code=status.HTTP_201_CREATED,
            response_model=model,
        )


@router.post(
    "/{subject_id}/{measurement_type}",
    include_in_schema=False,
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/{subject_id}/measurements/{measurement_type}",
    include_in_schema=False,
    status_code=status.HTTP_201_CREATED,
)
def reject_unsupported_measurement_type(
    subject_id: str, measurement_type: str, measurement: Measurement
) -> None:
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=f"Unsupported measurement type '{measurement_type}'",
    )


@router.get("/{subject_id}/{measurement_type}", include_in_schema=False)
def reject_unsupported_measurement_list(subject_id: str, measurement_type: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=f"Unsupported measurement type '{measurement_type}'",
    )
