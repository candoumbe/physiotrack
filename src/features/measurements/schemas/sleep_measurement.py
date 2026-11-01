from typing import Literal

from .measurement_base import MeasurementBase
from .measurement_type import MeasurementType


class SleepMeasurement(MeasurementBase):
    type: Literal[MeasurementType.SLEEP] = MeasurementType.SLEEP
    duration_minutes: int
    quality_score: float | None = None
