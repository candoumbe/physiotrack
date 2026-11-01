import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from .measurement import Measurement
from .measurement_integer import MeasurementInteger


class ActivityMeasurement(Measurement):
    __tablename__ = "activity_measurements"

    steps: Mapped[int] = mapped_column(MeasurementInteger)
    calories: Mapped[float | None] = mapped_column(sa.Double)
