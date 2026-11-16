from __future__ import annotations

from typing import Any, cast, get_args
from uuid import UUID

from physiotrack_migrator.models import Base
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import Engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from features.measurements.schemas import Measurement, MeasurementType
from physiotrack.database import DatabaseUnavailable

MeasurementAdapter = TypeAdapter(Measurement)
MeasurementORM = type[Base]


def _measurement_schema_types() -> set[MeasurementType]:
    variants = get_args(get_args(Measurement)[0])
    return {model.model_fields["type"].default for model in variants}


def _measurement_tables() -> dict[MeasurementType, MeasurementORM]:
    models_by_type: dict[MeasurementType, MeasurementORM] = {}
    for mapper in Base.registry.mappers:
        table_name = mapper.local_table.name
        if not table_name.endswith("_measurements"):
            continue
        type_name = table_name.removesuffix("_measurements")
        try:
            measurement_type = MeasurementType(type_name)
        except ValueError:
            continue
        models_by_type[measurement_type] = cast(MeasurementORM, mapper.class_)
    return models_by_type


class MeasurementService:
    """Persists measurements through the migrator's PostgreSQL ORM models."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        schema_types = _measurement_schema_types()
        table_models = _measurement_tables()
        self._models = {
            measurement_type: table_model
            for measurement_type, table_model in table_models.items()
            if measurement_type in schema_types
        }

    def create(self, subject_id: str, measurement: Measurement) -> Measurement:
        try:
            table_model = self._models[measurement.type]
            stored_measurement = measurement.model_copy(
                update={"subject_id": subject_id}
            )
            values = stored_measurement.model_dump(exclude={"type"})
            values["date_of_measure"] = values.pop("dateOfMeasure")

            with Session(self._engine) as session, session.begin():
                row = table_model(**values)
                session.add(row)
                session.flush()
                return MeasurementAdapter.validate_python(
                    self._schema_values(measurement.type, row)
                )
        except KeyError, SQLAlchemyError, ValidationError:
            raise DatabaseUnavailable(
                "Measurement storage is unavailable or inconsistent."
            ) from None

    def get(self, subject_id: str, measurement_id: str) -> Measurement | None:
        try:
            parsed_id = UUID(measurement_id)
        except ValueError:
            return None

        try:
            with Session(self._engine) as session:
                for measurement_type, table_model in self._models.items():
                    row = session.scalar(
                        select(table_model).where(
                            table_model.id == parsed_id,
                            table_model.subject_id == subject_id,
                        )
                    )
                    if row is not None:
                        return MeasurementAdapter.validate_python(
                            self._schema_values(measurement_type, row)
                        )
            return None
        except SQLAlchemyError, ValidationError:
            raise DatabaseUnavailable(
                "Measurement storage is unavailable or inconsistent."
            ) from None

    def list(
        self,
        subject_id: str,
        measurement_type: str | None,
        limit: int | None,
        offset: int,
    ) -> tuple[list[Measurement], int, int]:
        try:
            types = [
                (known_type, table_model)
                for known_type, table_model in self._models.items()
                if measurement_type is None or known_type.value == measurement_type
            ]
            with Session(self._engine) as session:
                records: list[tuple[Any, MeasurementType, Any]] = []
                for known_type, table_model in types:
                    rows = session.scalars(
                        select(table_model).where(table_model.subject_id == subject_id)
                    ).all()
                    records.extend((row.created_at, known_type, row) for row in rows)

                records.sort(key=lambda record: (record[0], record[2].id.int))
                total = len(records)
                effective_limit = total if limit is None else limit
                page = records[offset : offset + effective_limit]
                measurements = [
                    MeasurementAdapter.validate_python(
                        self._schema_values(known_type, row)
                    )
                    for _, known_type, row in page
                ]
                return measurements, total, effective_limit
        except SQLAlchemyError, ValidationError:
            raise DatabaseUnavailable(
                "Measurement storage is unavailable or inconsistent."
            ) from None

    @staticmethod
    def _schema_values(measurement_type: MeasurementType, row: Any) -> dict[str, Any]:
        values = {
            column.name: getattr(row, column.name)
            for column in row.__table__.columns
            if column.name != "created_at"
        }
        values["dateOfMeasure"] = values.pop("date_of_measure")
        values["type"] = measurement_type
        return values
