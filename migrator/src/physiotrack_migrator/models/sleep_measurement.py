import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from .measurement import Measurement
from .measurement_integer import MeasurementInteger


class SleepMeasurement(Measurement):
    __tablename__ = "sleep_measurements"

    duration_minutes: Mapped[int] = mapped_column(MeasurementInteger)
    quality_score: Mapped[float | None] = mapped_column(sa.Double)
