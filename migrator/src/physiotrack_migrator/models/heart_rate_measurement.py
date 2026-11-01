from sqlalchemy.orm import Mapped, mapped_column

from .measurement import Measurement
from .measurement_integer import MeasurementInteger


class HeartRateMeasurement(Measurement):
    __tablename__ = "heart_rate_measurements"

    bpm: Mapped[int] = mapped_column(MeasurementInteger)
