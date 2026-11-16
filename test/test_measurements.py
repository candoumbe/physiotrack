import sys
from importlib import import_module
from pathlib import Path
from typing import get_args

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from features.measurements import schemas
from features.measurements.schemas.measurement_registry import (
    plural_resource_name,
    resolve_measurement_type,
)
from main import create_app
from physiotrack.database import DatabaseConfigurationError, DatabaseSettings

SUPPORTED_MEASUREMENTS = [
    (
        "heart_rate",
        {
            "type": "heart_rate",
            "bpm": 72,
            "dateOfMeasure": "2026-09-13T12:00:00Z",
        },
    ),
    (
        "sleep",
        {
            "type": "sleep",
            "duration_minutes": 420,
            "dateOfMeasure": "2026-09-13T12:00:00Z",
        },
    ),
    (
        "activity",
        {
            "type": "activity",
            "steps": 1234,
            "dateOfMeasure": "2026-09-13T12:00:00Z",
        },
    ),
    (
        "blood_pressure",
        {
            "type": "blood_pressure",
            "systolic": 120,
            "diastolic": 80,
            "dateOfMeasure": "2026-09-13T12:00:00Z",
        },
    ),
]


@pytest.mark.parametrize(
    "name,module_name",
    [
        ("MeasurementType", "measurement_type"),
        ("MeasurementValue", "measurement_value"),
        ("MeasurementBase", "measurement_base"),
        ("HeartRateMeasurement", "heart_rate_measurement"),
        ("SleepMeasurement", "sleep_measurement"),
        ("ActivityMeasurement", "activity_measurement"),
        ("BloodPressureMeasurement", "blood_pressure_measurement"),
    ],
)
def test_schema_package_reexports(name, module_name):
    module = import_module(f"features.measurements.schemas.{module_name}")
    assert getattr(schemas, name) is getattr(module, name)


@pytest.mark.parametrize(
    "model_class,variant",
    [
        (schemas.HeartRateMeasurement, {"type": "heart_rate", "bpm": 72}),
        (schemas.SleepMeasurement, {"type": "sleep", "duration_minutes": 420}),
        (schemas.ActivityMeasurement, {"type": "activity", "steps": 1000}),
        (
            schemas.BloodPressureMeasurement,
            {"type": "blood_pressure", "systolic": 120, "diastolic": 80},
        ),
    ],
)
def test_schema_union_round_trip(model_class, variant):
    contract = TypeAdapter(schemas.Measurement)
    model = contract.validate_python(
        {**variant, "dateOfMeasure": "2026-10-30T15:25:42Z"}
    )
    assert type(model) is model_class
    assert contract.validate_json(contract.dump_json(model)) == model
    assert contract.json_schema()["discriminator"] == {
        "propertyName": "type",
        "mapping": {
            "heart_rate": "#/$defs/HeartRateMeasurement",
            "sleep": "#/$defs/SleepMeasurement",
            "activity": "#/$defs/ActivityMeasurement",
            "blood_pressure": "#/$defs/BloodPressureMeasurement",
        },
    }


def test_create_and_list_measurements_for_subject(client):
    subject_id = "subject-123"
    payload = {
        "type": "heart_rate",
        "bpm": 72,
        "dateOfMeasure": "2026-09-13T12:00:00Z",
    }

    response = client.post(f"/subjects/{subject_id}/measurements", json=payload)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["type"] == "heart_rate"
    assert body["subject_id"] == subject_id
    assert body["bpm"] == 72
    assert "id" in body
    assert body["dateOfMeasure"].endswith("Z") or body["dateOfMeasure"].endswith(
        "+00:00"
    )

    list_response = client.get(f"/subjects/{subject_id}/measurements")
    assert list_response.status_code == 200, list_response.text
    payload = list_response.json()
    items = payload["items"]
    assert len(items) == 1
    assert items[0]["id"] == body["id"]


def test_list_measurements_can_be_filtered_by_type(client):
    subject_id = "subject-456"
    client.post(
        f"/subjects/{subject_id}/measurements",
        json={
            "type": "sleep",
            "duration_minutes": 420,
            "quality_score": 0.8,
            "dateOfMeasure": "2026-09-13T08:00:00Z",
        },
    )
    client.post(
        f"/subjects/{subject_id}/measurements",
        json={
            "type": "activity",
            "steps": 12345,
            "calories": 320.5,
            "dateOfMeasure": "2026-09-13T18:30:00Z",
        },
    )

    sleep_response = client.get(f"/subjects/{subject_id}/measurements?type=sleep")
    assert sleep_response.status_code == 200, sleep_response.text
    sleep_items = sleep_response.json()["items"]
    assert len(sleep_items) == 1
    assert sleep_items[0]["type"] == "sleep"

    activity_response = client.get(f"/subjects/{subject_id}/measurements?type=activity")
    assert activity_response.status_code == 200, activity_response.text
    activity_items = activity_response.json()["items"]
    assert len(activity_items) == 1
    assert activity_items[0]["type"] == "activity"


def test_list_measurements_supports_pagination(client):
    subject_id = "subject-789"
    for idx in range(5):
        client.post(
            f"/subjects/{subject_id}/measurements",
            json={
                "type": "heart_rate",
                "bpm": 70 + idx,
                "dateOfMeasure": f"2026-09-13T12:{idx:02d}:00Z",
            },
        )

    response = client.get(f"/subjects/{subject_id}/measurements?limit=2&offset=1")
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["items"]) == 2
    assert [item["bpm"] for item in body["items"]] == [71, 72]
    assert body["pagination"]["total"] == 5
    assert body["pagination"]["limit"] == 2
    assert body["pagination"]["offset"] == 1
    assert "next" in body["links"]
    assert "previous" in body["links"]
    assert "offset=3" in body["links"]["next"]
    assert "offset=0" in body["links"]["previous"]


@pytest.mark.parametrize("measurement_type,payload", SUPPORTED_MEASUREMENTS)
def test_typed_measurement_routes_dispatch_supported_types(
    client, measurement_type, payload
):
    subject_id = f"typed-{measurement_type}"
    resource_name = plural_resource_name(schemas.MeasurementType(measurement_type))

    create_response = client.post(
        f"/subjects/{subject_id}/{resource_name}/", json=payload
    )

    assert create_response.status_code == 201, create_response.text
    created = create_response.json()
    assert created["type"] == measurement_type
    assert created["subject_id"] == subject_id
    assert create_response.headers["location"] == (
        f"/subjects/{subject_id}/measurements/{created['id']}"
    )

    list_response = client.get(f"/subjects/{subject_id}/{resource_name}/")

    assert list_response.status_code == 200, list_response.text
    body = list_response.json()
    assert [item["id"] for item in body["items"]] == [created["id"]]
    assert body["pagination"] == {"total": 1, "limit": 1, "offset": 0}
    assert body["links"] == {"next": None, "previous": None}


def test_typed_routes_cover_the_canonical_measurement_types(client):
    measurement_union = get_args(schemas.Measurement)[0]
    registered_types = {
        model.model_fields["type"].default.value
        for model in get_args(measurement_union)
    }

    assert registered_types == {
        measurement_type.value for measurement_type in schemas.MeasurementType
    }
    assert registered_types == {
        measurement_type for measurement_type, _ in SUPPORTED_MEASUREMENTS
    }
    for measurement_type in schemas.MeasurementType:
        resource_name = plural_resource_name(measurement_type)
        assert resolve_measurement_type(resource_name) is measurement_type
        response = client.get(f"/subjects/empty/{resource_name}/")
        assert response.status_code == 200, response.text


def test_blood_pressures_plural_collection_path(client):
    response = client.get("/subjects/blood-pressure/blood_pressures/")

    assert plural_resource_name(schemas.MeasurementType.BLOOD_PRESSURE) == (
        "blood_pressures"
    )
    assert response.status_code == 200, response.text


def test_typed_routes_keep_canonical_singular_aliases(client):
    subject_id = "typed-singular-alias"
    payload = SUPPORTED_MEASUREMENTS[-1][1]

    create_response = client.post(
        f"/subjects/{subject_id}/blood_pressure/", json=payload
    )
    list_response = client.get(f"/subjects/{subject_id}/blood_pressure")

    assert create_response.status_code == 201, create_response.text
    assert list_response.status_code == 200, list_response.text
    assert list_response.json()["items"][0]["id"] == create_response.json()["id"]


def test_typed_measurement_creation_keeps_measurements_path_compatible(client):
    subject_id = "typed-legacy-path"
    payload = SUPPORTED_MEASUREMENTS[-1][1]

    create_response = client.post(
        f"/subjects/{subject_id}/measurements/blood_pressure", json=payload
    )

    assert create_response.status_code == 201, create_response.text
    assert create_response.json()["type"] == "blood_pressure"


def test_typed_measurement_creation_rejects_mismatched_and_invalid_payloads(client):
    subject_id = "typed-invalid"
    mismatch = client.post(
        f"/subjects/{subject_id}/blood_pressures/",
        json=SUPPORTED_MEASUREMENTS[0][1],
    )
    invalid = client.post(
        f"/subjects/{subject_id}/blood_pressures/",
        json={
            "type": "blood_pressure",
            "systolic": 120,
            "dateOfMeasure": "2026-09-13T12:00:00Z",
        },
    )

    assert mismatch.status_code == 422
    assert invalid.status_code == 422
    assert client.get(f"/subjects/{subject_id}/measurements").json()["items"] == []


@pytest.mark.parametrize("unsupported_type", ["heights", "unknown"])
def test_typed_routes_reject_unsupported_measurement_types(client, unsupported_type):
    post_response = client.post(
        f"/subjects/unsupported/{unsupported_type}/",
        json=SUPPORTED_MEASUREMENTS[0][1],
    )
    get_response = client.get(f"/subjects/unsupported/{unsupported_type}/")

    assert post_response.status_code == 422
    assert get_response.status_code == 422


def test_get_measurement_by_id_uses_service_storage(client):
    subject_id = "single-measurement"
    create_response = client.post(
        f"/subjects/{subject_id}/measurements",
        json=SUPPORTED_MEASUREMENTS[0][1],
    )
    measurement_id = create_response.json()["id"]

    response = client.get(f"/subjects/{subject_id}/measurements/{measurement_id}")

    assert response.status_code == 200, response.text
    assert response.json()["id"] == measurement_id


def test_measurement_persists_after_api_restarts(api_database_environment):
    subject_id = "persisted-subject"
    payload = SUPPORTED_MEASUREMENTS[-1][1]
    with TestClient(create_app()) as writer:
        create_response = writer.post(
            f"/subjects/{subject_id}/measurements/blood_pressures",
            json=payload,
        )
        assert create_response.status_code == 201, create_response.text
        measurement_id = create_response.json()["id"]

    with TestClient(create_app()) as reader:
        response = reader.get(f"/subjects/{subject_id}/measurements/{measurement_id}")

    assert response.status_code == 200, response.text
    assert response.json()["id"] == measurement_id


def test_database_configuration_requires_explicit_apphost_fields():
    with pytest.raises(DatabaseConfigurationError, match="required database settings"):
        DatabaseSettings.from_environment({})
