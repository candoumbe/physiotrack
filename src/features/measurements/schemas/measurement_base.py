from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class MeasurementBase(BaseModel):
    """Fields shared by every physiological measurement."""

    id: UUID = Field(default_factory=uuid4)
    subject_id: str | None = Field(default=None, min_length=1)
    dateOfMeasure: datetime
