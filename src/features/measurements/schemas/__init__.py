"""Type-specific measurement schemas and the generic discriminated union."""

from typing import Annotated

from pydantic import Field

from .activity_measurement import ActivityMeasurement, ActivityMeasurementWithType
from .blood_pressure_measurement import (
    BloodPressureMeasurement,
    BloodPressureMeasurementWithType,
)
from .heart_rate_measurement import HeartRateMeasurement, HeartRateMeasurementWithType
from .measurement_base import MeasurementBase
from .measurement_type import MeasurementType
from .measurement_value import MeasurementValue
from .sleep_measurement import SleepMeasurement, SleepMeasurementWithType

Measurement = Annotated[
    HeartRateMeasurementWithType
    | SleepMeasurementWithType
    | ActivityMeasurementWithType
    | BloodPressureMeasurementWithType,
    Field(discriminator="type"),
]

MEASUREMENT_MODELS = {
    MeasurementType.HEART_RATE: HeartRateMeasurement,
    MeasurementType.SLEEP: SleepMeasurement,
    MeasurementType.ACTIVITY: ActivityMeasurement,
    MeasurementType.BLOOD_PRESSURE: BloodPressureMeasurement,
}

__all__ = [
    "MEASUREMENT_MODELS",
    "ActivityMeasurement",
    "BloodPressureMeasurement",
    "HeartRateMeasurement",
    "Measurement",
    "MeasurementBase",
    "MeasurementType",
    "MeasurementValue",
    "SleepMeasurement",
]
