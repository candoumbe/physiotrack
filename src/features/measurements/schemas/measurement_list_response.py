from pydantic import BaseModel

from . import Measurement


class MeasurementPagination(BaseModel):
    total: int
    limit: int
    offset: int


class MeasurementLinks(BaseModel):
    next: str | None
    previous: str | None


class MeasurementListResponse(BaseModel):
    items: list[Measurement]
    pagination: MeasurementPagination
    links: MeasurementLinks
