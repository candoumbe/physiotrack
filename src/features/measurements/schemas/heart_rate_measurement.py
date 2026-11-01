from typing import Literal

from .measurement_base import MeasurementBase
from .measurement_type import MeasurementType


class HeartRateMeasurement(MeasurementBase):
    type: Literal[MeasurementType.HEART_RATE] = MeasurementType.HEART_RATE
    bpm: int
