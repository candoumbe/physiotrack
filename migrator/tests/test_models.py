from datetime import datetime
from importlib import import_module

import pytest
from sqlalchemy import inspect
from sqlalchemy.orm import configure_mappers

from physiotrack_migrator import models


@pytest.mark.parametrize(
    "name,module_name",
    [
        ("Base", "base"),
        ("Measurement", "measurement"),
        ("MeasurementInteger", "measurement_integer"),
        ("MeasurementDateTime", "measurement_date_time"),
        ("HeartRateMeasurement", "heart_rate_measurement"),
        ("SleepMeasurement", "sleep_measurement"),
        ("ActivityMeasurement", "activity_measurement"),
        ("BloodPressureMeasurement", "blood_pressure_measurement"),
    ],
)
def test_model_package_reexports(name, module_name):
    module = import_module(f"physiotrack_migrator.models.{module_name}")
    assert getattr(models, name) is getattr(module, name)


def test_package_import_registers_dedicated_tables():
    configure_mappers()
    assert len(models.Base.registry.mappers) == 4
    expected = {
        "public.heart_rate_measurements": {"bpm"},
        "public.sleep_measurements": {"duration_minutes", "quality_score"},
        "public.activity_measurements": {"steps", "calories"},
        "public.blood_pressure_measurements": {"systolic", "diastolic", "unit"},
    }
    assert set(models.Base.metadata.tables) == set(expected)
    assert inspect(models.Measurement, raiseerr=False) is None
    for name, fields in expected.items():
        table = models.Base.metadata.tables[name]
        assert set(table.c.keys()) == {"id", "subject_id", "date_of_measure", *fields}
        for column in table.c:
            assert column.nullable == (
                column.name in {"subject_id", "quality_score", "calories"}
            )


@pytest.mark.parametrize("value", [None, "0", str(-(10**80)), str(10**80)])
def test_measurement_integer_preserves_results(value):
    expected = None if value is None else int(value)
    assert models.MeasurementInteger().process_result_value(value, None) == expected


@pytest.mark.parametrize(
    "value",
    [
        None,
        datetime.fromisoformat("2026-10-30T15:25:42.123456"),
        datetime.fromisoformat("2026-10-30T15:25:42.123456+05:30"),
    ],
)
def test_measurement_datetime_round_trip(value):
    decorator = models.MeasurementDateTime()
    stored = decorator.process_bind_param(value, None)
    assert stored == (None if value is None else value.isoformat())
    assert decorator.process_result_value(stored, None) == value
