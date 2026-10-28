import importlib.util
import math
import socket
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.operations import Operations
from pydantic import TypeAdapter
from sqlalchemy.exc import IntegrityError

from physiotrack_migrator import cli
from physiotrack_migrator.config import Settings
from physiotrack_migrator.runner import TargetError, migrate

pytestmark = pytest.mark.integration
HEAD = "0001_measurements"
PROJECT = Path(__file__).resolve().parents[1]


def run_cli(database, *args, cwd=None, environ=None):
    return subprocess.run(
        [str(Path(sys.executable).with_name("physiotrack-migrator")), *args],
        cwd=cwd or PROJECT,
        env=database.environ if environ is None else environ,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )


def settings(database):
    return Settings.from_environ(database.environ)


def schema(engine):
    inspector = sa.inspect(engine)
    tables = inspector.get_table_names(schema="public")
    return {
        name: (
            [
                (column["name"], str(column["type"]), column["nullable"])
                for column in inspector.get_columns(name)
            ],
            sorted(
                (constraint["name"], constraint["sqltext"])
                for constraint in inspector.get_check_constraints(name)
            ),
            inspector.get_pk_constraint(name)["constrained_columns"],
        )
        for name in tables
    }


def test_up_up_down_down_up_introspected(database, engine, tmp_path):
    assert schema(engine) == {}
    assert run_cli(database, "status").stdout.strip() == "revision: base"
    assert schema(engine) == {}
    initial = None
    for action, expected in [
        ("up", HEAD),
        ("up", HEAD),
        ("down", "base"),
        ("down", "base"),
        ("up", HEAD),
    ]:
        result = run_cli(database, action, cwd=tmp_path)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == f"revision: {expected}"
        result = run_cli(database, "status", cwd=PROJECT.parents[1])
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == f"revision: {expected}"
        current = schema(engine)
        with engine.connect() as connection:
            revisions = connection.scalars(
                sa.text("SELECT version_num FROM public.alembic_version")
            ).all()
            assert (
                connection.scalar(sa.text("SELECT current_database()"))
                == database.url.database
            )
        if expected == "base":
            assert set(current) == {"alembic_version"}
            assert revisions == []
        else:
            assert set(current) == {"measurements", "alembic_version"}
            assert revisions == [HEAD]
            assert len(current["measurements"][0]) == 12
            assert len(current["measurements"][1]) == 8
            assert current["measurements"][2] == ["id"]
            if initial is None:
                initial = current
            assert current == initial


@pytest.fixture
def measurements(database, engine):
    migrate(settings(database), "up", "head")
    return sa.Table(
        "measurements", sa.MetaData(), schema="public", autoload_with=engine
    )


def adapter():
    path = PROJECT.parent / "src/features/measurements/schemas.py"
    spec = importlib.util.spec_from_file_location("measurement_contract", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return TypeAdapter(module.Measurement)


@pytest.mark.parametrize(
    "variant",
    [
        {"type": "heart_rate", "bpm": 72},
        {"type": "heart_rate", "bpm": -(10**80)},
        {"type": "sleep", "duration_minutes": 420},
        {"type": "sleep", "duration_minutes": -1, "quality_score": 8.25},
        {"type": "activity", "steps": 10**80},
        {"type": "activity", "steps": 0, "calories": -1.5},
        {"type": "blood_pressure", "systolic": 120, "diastolic": 80},
        {
            "type": "blood_pressure",
            "systolic": -(10**80),
            "diastolic": 10**80,
            "unit": "mmHg",
        },
    ],
)
@pytest.mark.parametrize(
    "date",
    [
        "2026-10-28T11:58:53.123456",
        "2026-10-28T11:58:53.123456+05:30",
        "2026-10-28T11:58:53Z",
    ],
)
@pytest.mark.parametrize("subject", [None, "synthetic-subject"])
def test_pydantic_variants_round_trip(variant, date, subject, measurements, engine):
    contract = adapter()
    model = contract.validate_python(
        {**variant, "dateOfMeasure": date, "subject_id": subject}
    )
    values = model.model_dump()
    values["date_of_measure"] = values.pop("dateOfMeasure").isoformat()
    values["type"] = model.type.value
    with engine.begin() as connection:
        connection.execute(measurements.insert().values(**values))
        stored = dict(connection.execute(sa.select(measurements)).mappings().one())
    assert stored["date_of_measure"] == model.dateOfMeasure.isoformat()
    stored["dateOfMeasure"] = stored.pop("date_of_measure")
    assert contract.validate_python(stored) == model


@pytest.mark.parametrize(
    "changes",
    [
        {"type": "unknown"},
        {"bpm": None},
        {"date_of_measure": None},
        {"id": None},
        {"subject_id": ""},
        {"steps": 1},
        {"quality_score": 0.5},
        {"unit": "mmHg"},
        {"type": "sleep", "duration_minutes": 1},
        {"type": "activity", "steps": 1},
        {"type": "blood_pressure", "bpm": None, "systolic": 120, "diastolic": 80},
        {
            "type": "blood_pressure",
            "bpm": None,
            "systolic": 120,
            "diastolic": 80,
            "unit": "other",
        },
        {"type": "blood_pressure", "bpm": None, "systolic": 120, "unit": "mmHg"},
        {"type": "sleep", "bpm": None},
        {"type": "activity", "bpm": None},
        *[{"bpm": value} for value in ("1.5", "NaN", "Infinity", "-Infinity")],
        *[
            {"type": "sleep", "bpm": None, "duration_minutes": value}
            for value in ("1.5", "NaN", "Infinity", "-Infinity")
        ],
        *[
            {"type": "activity", "bpm": None, "steps": value}
            for value in ("1.5", "NaN", "Infinity", "-Infinity")
        ],
        *[
            {
                "type": "blood_pressure",
                "bpm": None,
                "unit": "mmHg",
                "systolic": value,
                "diastolic": 80,
            }
            for value in ("1.5", "NaN", "Infinity", "-Infinity")
        ],
        *[
            {
                "type": "blood_pressure",
                "bpm": None,
                "unit": "mmHg",
                "systolic": 120,
                "diastolic": value,
            }
            for value in ("1.5", "NaN", "Infinity", "-Infinity")
        ],
    ],
)
def test_constraints_reject_invalid_variants(changes, measurements, engine):
    row = {
        "id": uuid4(),
        "type": "heart_rate",
        "bpm": 72,
        "date_of_measure": "2026-10-28T11:58:53",
        **changes,
    }
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(measurements.insert().values(**row))


def test_primary_key_and_destructive_rollback(database, measurements, engine):
    row = {
        "id": uuid4(),
        "type": "heart_rate",
        "bpm": 72,
        "date_of_measure": "2026-10-28T11:58:53",
    }
    with engine.begin() as connection:
        connection.execute(measurements.insert().values(**row))
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(measurements.insert().values(**row))
    migrate(settings(database), "down", "base")
    migrate(settings(database), "up", "head")
    with engine.connect() as connection:
        assert (
            connection.scalar(sa.select(sa.func.count()).select_from(measurements)) == 0
        )


@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan")])
def test_optional_float_contract_does_not_invent_finite_bounds(
    value, measurements, engine
):
    model = adapter().validate_python(
        {
            "type": "sleep",
            "duration_minutes": 1,
            "quality_score": value,
            "dateOfMeasure": "2026-10-28T11:58:53",
        }
    )
    with engine.begin() as connection:
        connection.execute(
            measurements.insert().values(
                id=model.id,
                type="sleep",
                duration_minutes=1,
                quality_score=value,
                date_of_measure=model.dateOfMeasure.isoformat(),
            )
        )
        stored = connection.scalar(sa.select(measurements.c.quality_score))
    assert math.isnan(stored) if math.isnan(value) else stored == value


@pytest.mark.parametrize(
    "ddl",
    [
        "CREATE TABLE public.foreign_table (id integer)",
        "CREATE SCHEMA foreign_schema",
        "CREATE SCHEMA pgforeign",
        "CREATE SEQUENCE public.foreign_sequence",
        "CREATE TYPE public.foreign_enum AS ENUM ('a')",
        "CREATE TYPE public.foreign_composite AS (id integer)",
        "CREATE VIEW public.foreign_view AS SELECT 1 AS id",
        "CREATE FUNCTION public.foreign_function() RETURNS integer LANGUAGE sql AS 'SELECT 1'",
        "CREATE TABLE public.alembic_version (version_num varchar(32) PRIMARY KEY)",
    ],
)
def test_reject_foreign_objects_without_ddl(database, engine, ddl):
    with engine.begin() as connection:
        connection.execute(sa.text(ddl))
    before = schema(engine)
    for action in ("status", "up", "down"):
        result = run_cli(database, action)
        assert result.returncode == 1
        assert "target rejected" in result.stderr
        assert schema(engine) == before


def test_foreign_object_after_migration_blocks_rollback(database, measurements, engine):
    with engine.begin() as connection:
        connection.execute(sa.text("CREATE TABLE public.foreign_table (id integer)"))
    assert run_cli(database, "down").returncode == 1
    assert "measurements" in schema(engine)


def test_check_connected_name_and_role(database, engine):
    with pytest.raises(TargetError):
        migrate(Settings(database.url, "different_expected_name"), "up", "head")
    with pytest.raises(TargetError):
        migrate(Settings(database.admin_url, database.url.database), "up", "head")
    assert schema(engine) == {}


@pytest.mark.parametrize(
    "action, operation", [("up", "create_table"), ("down", "drop_table")]
)
def test_transactional_ddl_failure(
    database, engine, monkeypatch, capsys, action, operation
):
    if action == "down":
        migrate(settings(database), "up", "head")
    before = schema(engine)
    original = getattr(Operations, operation)

    def failing(self, *args, **kwargs):
        original(self, *args, **kwargs)
        raise RuntimeError("synthetic-secret injected DDL failure")

    with monkeypatch.context() as patch:
        patch.setattr(Operations, operation, failing)
        for key, value in database.environ.items():
            if key.startswith("PHYSIOTRACK_MIGRATOR_"):
                patch.setenv(key, value)
        assert cli.main([action]) == 1
    assert "synthetic-secret" not in capsys.readouterr().err
    assert schema(engine) == before
    assert (
        run_cli(database, "status").stdout.strip()
        == f"revision: {HEAD if action == 'down' else 'base'}"
    )
    assert run_cli(database, action).returncode == 0


def test_unknown_revision_is_redacted(database, engine):
    result = run_cli(database, "up", "--revision", "synthetic-secret")
    assert result.returncode == 1
    assert "synthetic-secret" not in result.stderr + result.stdout
    assert schema(engine) == {}


def test_denied_access_is_redacted(database, engine):
    environment = database.environ
    environment["PHYSIOTRACK_MIGRATOR_DATABASE_URL"] = database.url.set(
        password="synthetic-secret"
    ).render_as_string(hide_password=False)
    result = run_cli(database, "up", environ=environment)
    assert result.returncode == 1
    assert "synthetic-secret" not in result.stderr + result.stdout
    assert "Traceback" not in result.stderr
    assert schema(engine) == {}


def test_denied_ddl_is_redacted(database, engine):
    admin = sa.create_engine(database.admin_url)
    try:
        with admin.begin() as connection:
            connection.execute(
                sa.text("REVOKE CREATE ON SCHEMA public FROM PUBLIC, pg_database_owner")
            )
        result = run_cli(database, "up")
        assert result.returncode == 1
        assert "Migration failed" in result.stderr
        assert "Traceback" not in result.stderr
        assert database.url.password not in result.stderr + result.stdout
        assert schema(engine) == {}
    finally:
        admin.dispose()


def test_unknown_stored_revision_is_rejected(database, measurements, engine):
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "UPDATE public.alembic_version SET version_num = 'foreign_revision'"
            )
        )
    for action in ("status", "up", "down"):
        result = run_cli(database, action)
        assert result.returncode == 1
        assert "target rejected" in result.stderr
    assert "measurements" in schema(engine)


def test_unavailable_database_is_bounded_and_redacted(database):
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen()
        environment = database.environ
        environment["PHYSIOTRACK_MIGRATOR_DATABASE_URL"] = database.url.set(
            port=server.getsockname()[1], password="synthetic-secret"
        ).render_as_string(hide_password=False)
        started = time.monotonic()
        result = run_cli(database, "up", environ=environment)
    assert result.returncode == 1
    assert time.monotonic() - started < 12
    assert "synthetic-secret" not in result.stderr + result.stdout


def test_explicit_revision_targets(database, engine):
    assert run_cli(database, "up", "--revision", HEAD).returncode == 0
    assert run_cli(database, "down", "--revision", HEAD).returncode == 0
    assert "measurements" in schema(engine)
    assert run_cli(database, "down", "--revision", "base").returncode == 0
    assert "measurements" not in schema(engine)
