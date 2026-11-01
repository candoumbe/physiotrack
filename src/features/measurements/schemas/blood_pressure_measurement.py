from typing import Literal

from .measurement_base import MeasurementBase
from .measurement_type import MeasurementType


class BloodPressureMeasurement(MeasurementBase):
    type: Literal[MeasurementType.BLOOD_PRESSURE] = MeasurementType.BLOOD_PRESSURE
    systolic: int
    diastolic: int
    unit: Literal["mmHg"] = "mmHg"
