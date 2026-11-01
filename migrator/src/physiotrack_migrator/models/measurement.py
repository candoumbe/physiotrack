from datetime import datetime
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

from .base import Base
from .measurement_date_time import MeasurementDateTime


class Measurement(Base):
    __abstract__ = True

    id: Mapped[UUID] = mapped_column(
        sa.UUID, default=uuid4, primary_key=True, sort_order=-3
    )
    subject_id: Mapped[str | None] = mapped_column(sa.Text, sort_order=-2)
    date_of_measure: Mapped[datetime] = mapped_column(
        MeasurementDateTime, sort_order=-1
    )

    @declared_attr.directive
    def __table_args__(cls):
        return (
            sa.PrimaryKeyConstraint("id", name=f"pk_{cls.__tablename__}"),
            sa.CheckConstraint(
                "subject_id IS NULL OR length(subject_id) > 0",
                name="ck_subject_nonempty",
            ),
            *[
                sa.CheckConstraint(
                    f"{column} NOT IN ('NaN'::numeric, 'Infinity'::numeric, "
                    f"'-Infinity'::numeric) AND {column} = trunc({column})",
                    name=f"ck_{column}_integer",
                )
                for column in (
                    "bpm",
                    "duration_minutes",
                    "steps",
                    "systolic",
                    "diastolic",
                )
                if hasattr(cls, column)
            ],
            *(
                [sa.CheckConstraint("unit = 'mmHg'", name="ck_unit_mmhg")]
                if hasattr(cls, "unit")
                else []
            ),
            {"schema": "public", "comment": "physiotrack-migrator"},
        )
