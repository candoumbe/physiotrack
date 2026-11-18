from pydantic import BaseModel

from . import Measurement


class MeasurementLink(BaseModel):
    href: str
    rel: str


class MeasurementLinks(BaseModel):
    prev: MeasurementLink | None
    next: MeasurementLink | None
    first: MeasurementLink
    last: MeasurementLink


class MeasurementListResponse(BaseModel):
    items: list[Measurement]
    total: int
    links: MeasurementLinks
