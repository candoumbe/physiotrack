from pydantic import BaseModel


class MeasurementLink(BaseModel):
    href: str
    rel: str


class MeasurementLinks(BaseModel):
    prev: MeasurementLink | None
    next: MeasurementLink | None
    first: MeasurementLink
    last: MeasurementLink


class MeasurementListResponse[MeasurementItem](BaseModel):
    items: list[MeasurementItem]
    total: int
    links: MeasurementLinks
