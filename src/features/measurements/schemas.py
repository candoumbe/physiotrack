"""Common schema for physiological measurements and its type-specific variants.

Skeleton only — illustrates the discriminated-union structure. Full set of
fields per measurement type will be finalized by Backend Dev / Data Engineer.
"""

from datetime import datetime
from enum import Enum
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class MeasurementType(str, Enum):
    HEART_RATE = "heart_rate"
    SLEEP = "sleep"
    ACTIVITY = "activity"


class MeasurementBase(BaseModel):
    """Fields shared by every physiological measurement."""

    id: UUID = Field(default_factory=uuid4)
    subject_id: str = Field(min_length=1)
    dateOfMeasure: datetime


class HeartRateMeasurement(MeasurementBase):
    type: Literal[MeasurementType.HEART_RATE] = MeasurementType.HEART_RATE
    bpm: int


class SleepMeasurement(MeasurementBase):
    type: Literal[MeasurementType.SLEEP] = MeasurementType.SLEEP
    duration_minutes: int
    quality_score: float | None = None


class ActivityMeasurement(MeasurementBase):
    type: Literal[MeasurementType.ACTIVITY] = MeasurementType.ACTIVITY
    steps: int
    calories: float | None = None


Measurement = Annotated[
    HeartRateMeasurement | SleepMeasurement | ActivityMeasurement,
    Field(discriminator="type"),
]
