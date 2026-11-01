from typing import Literal

from .measurement_base import MeasurementBase
from .measurement_type import MeasurementType


class ActivityMeasurement(MeasurementBase):
    type: Literal[MeasurementType.ACTIVITY] = MeasurementType.ACTIVITY
    steps: int
    calories: float | None = None
