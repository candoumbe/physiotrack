import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from .measurement import Measurement
from .measurement_integer import MeasurementInteger


class BloodPressureMeasurement(Measurement):
    __tablename__ = "blood_pressure_measurements"

    systolic: Mapped[int] = mapped_column(MeasurementInteger)
    diastolic: Mapped[int] = mapped_column(MeasurementInteger)
    unit: Mapped[str] = mapped_column(sa.Text, default="mmHg")
