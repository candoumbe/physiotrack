from typing import Literal

from .measurement_base import MeasurementBase
from .measurement_type import MeasurementType


class ActivityMeasurement(MeasurementBase):
    steps: int
    calories: float | None = None


class ActivityMeasurementWithType(ActivityMeasurement):
    type: Literal[MeasurementType.ACTIVITY] = MeasurementType.ACTIVITY
