from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any, cast, get_args
from uuid import UUID

from physiotrack_migrator.models import Base
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import Engine, func, literal, select, union_all
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from features.measurements.schemas import Measurement, MeasurementType
from physiotrack.database import DatabaseUnavailable

MeasurementAdapter = TypeAdapter(Measurement)
MeasurementORM = type[Base]
DEFAULT_MEASUREMENT_LIMIT = 50
DEFAULT_MAX_MEASUREMENT_LIMIT = 200
MAX_MEASUREMENT_LIMIT_ENVIRONMENT_VARIABLE = "PHYSIOTRACK_MEASUREMENTS_MAX_LIMIT"


class MeasurementPaginationConfigurationError(RuntimeError):
    """The configured maximum measurement limit is invalid."""


def max_measurement_limit_from_environment(
    environ: Mapping[str, str] | None = None,
) -> int:
    values = os.environ if environ is None else environ
    raw_limit = values.get(MAX_MEASUREMENT_LIMIT_ENVIRONMENT_VARIABLE)
    if raw_limit is None:
        return DEFAULT_MAX_MEASUREMENT_LIMIT
    if not raw_limit.isascii() or not raw_limit.isdecimal():
        raise MeasurementPaginationConfigurationError(
            f"{MAX_MEASUREMENT_LIMIT_ENVIRONMENT_VARIABLE} must be a positive integer."
        )

    try:
        max_limit = int(raw_limit)
    except ValueError:
        raise MeasurementPaginationConfigurationError(
            f"{MAX_MEASUREMENT_LIMIT_ENVIRONMENT_VARIABLE} must be a positive integer."
        ) from None
    if max_limit < 1:
        raise MeasurementPaginationConfigurationError(
            f"{MAX_MEASUREMENT_LIMIT_ENVIRONMENT_VARIABLE} must be a positive integer."
        )
    return max_limit


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

    def __init__(
        self, engine: Engine, *, max_limit: int = DEFAULT_MAX_MEASUREMENT_LIMIT
    ) -> None:
        if (
            isinstance(max_limit, bool)
            or not isinstance(max_limit, int)
            or max_limit < 1
        ):
            raise MeasurementPaginationConfigurationError(
                "The maximum measurement limit must be a positive integer."
            )
        self._engine = engine
        self._max_limit = max_limit
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

    def get(
        self, subject_id: str, measurement_type: MeasurementType, measurement_id: str
    ) -> Measurement | None:
        try:
            parsed_id = UUID(measurement_id)
        except ValueError:
            return None

        try:
            table_model = self._models[measurement_type]
            with Session(self._engine) as session:
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
        except KeyError, SQLAlchemyError, ValidationError:
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
        effective_limit = min(
            DEFAULT_MEASUREMENT_LIMIT if limit is None else limit,
            self._max_limit,
        )
        try:
            types = [
                (known_type, table_model)
                for known_type, table_model in self._models.items()
                if measurement_type is None or known_type.value == measurement_type
            ]
            if not types:
                return [], 0, effective_limit

            with Session(self._engine) as session:
                records = union_all(
                    *(
                        select(
                            table_model.id.label("id"),
                            table_model.created_at.label("created_at"),
                            literal(known_type.value).label("measurement_type"),
                        ).where(table_model.subject_id == subject_id)
                        for known_type, table_model in types
                    )
                ).subquery()
                total = session.scalar(select(func.count()).select_from(records)) or 0
                page = session.execute(
                    select(records.c.id, records.c.measurement_type)
                    .order_by(records.c.created_at, records.c.id)
                    .offset(offset)
                    .limit(effective_limit)
                ).all()

                rows_by_key: dict[tuple[str, Any], Any] = {}
                for known_type, table_model in types:
                    ids = [
                        row.id
                        for row in page
                        if row.measurement_type == known_type.value
                    ]
                    if not ids:
                        continue
                    rows = session.scalars(
                        select(table_model).where(
                            table_model.subject_id == subject_id,
                            table_model.id.in_(ids),
                        )
                    ).all()
                    rows_by_key.update(
                        ((known_type.value, row.id), row) for row in rows
                    )

                measurements = [
                    MeasurementAdapter.validate_python(
                        self._schema_values(
                            MeasurementType(row.measurement_type),
                            rows_by_key[(row.measurement_type, row.id)],
                        )
                    )
                    for row in page
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
