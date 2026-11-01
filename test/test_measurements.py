import sys
from importlib import import_module
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from features.measurements import schemas
from main import app

client = TestClient(app)


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


def test_create_and_list_measurements_for_subject():
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


def test_list_measurements_can_be_filtered_by_type():
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


def test_list_measurements_supports_pagination():
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
