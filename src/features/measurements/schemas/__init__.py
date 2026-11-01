"""Common schema for physiological measurements and its type-specific variants.

Skeleton only - illustrates the discriminated-union structure. Full set of
fields per measurement type will be finalized by Backend Dev / Data Engineer.
"""

from typing import Annotated

from pydantic import Field

from .activity_measurement import ActivityMeasurement
from .blood_pressure_measurement import BloodPressureMeasurement
from .heart_rate_measurement import HeartRateMeasurement
from .measurement_base import MeasurementBase
from .measurement_type import MeasurementType
from .measurement_value import MeasurementValue
from .sleep_measurement import SleepMeasurement

Measurement = Annotated[
    HeartRateMeasurement
    | SleepMeasurement
    | ActivityMeasurement
    | BloodPressureMeasurement,
    Field(discriminator="type"),
]

__all__ = [
    "ActivityMeasurement",
    "BloodPressureMeasurement",
    "HeartRateMeasurement",
    "Measurement",
    "MeasurementBase",
    "MeasurementType",
    "MeasurementValue",
    "SleepMeasurement",
]
