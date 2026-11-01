from enum import Enum


class MeasurementType(str, Enum):
    HEART_RATE = "heart_rate"
    SLEEP = "sleep"
    ACTIVITY = "activity"
    BLOOD_PRESSURE = "blood_pressure"
