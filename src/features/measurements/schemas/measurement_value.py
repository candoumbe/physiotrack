from pydantic import BaseModel


class MeasurementValue(BaseModel):
    """Base class for type-specific measurement values."""

    value: float | int
    unit: str | None = None
