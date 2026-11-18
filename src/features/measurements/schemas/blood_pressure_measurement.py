from typing import Literal

from .measurement_base import MeasurementBase
from .measurement_type import MeasurementType


class BloodPressureMeasurement(MeasurementBase):
    systolic: int
    diastolic: int
    unit: Literal["mmHg"] = "mmHg"


class BloodPressureMeasurementWithType(BloodPressureMeasurement):
    type: Literal[MeasurementType.BLOOD_PRESSURE] = MeasurementType.BLOOD_PRESSURE
