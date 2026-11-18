import sys
from importlib import import_module
from pathlib import Path
from typing import get_args

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter, ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from features.measurements import schemas
from features.measurements.schemas.measurement_registry import (
    plural_resource_name,
    resolve_measurement_type,
)
from features.measurements.service import (
    MeasurementPaginationConfigurationError,
    max_measurement_limit_from_environment,
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
    "model_class,generic_model_class,variant",
    [
        (
            schemas.HeartRateMeasurement,
            schemas.HeartRateMeasurementWithType,
            {"type": "heart_rate", "bpm": 72},
        ),
        (
            schemas.SleepMeasurement,
            schemas.SleepMeasurementWithType,
            {"type": "sleep", "duration_minutes": 420},
        ),
        (
            schemas.ActivityMeasurement,
            schemas.ActivityMeasurementWithType,
            {"type": "activity", "steps": 1000},
        ),
        (
            schemas.BloodPressureMeasurement,
            schemas.BloodPressureMeasurementWithType,
            {"type": "blood_pressure", "systolic": 120, "diastolic": 80},
        ),
    ],
)
def test_schema_union_round_trip(model_class, generic_model_class, variant):
    contract = TypeAdapter(schemas.Measurement)
    model = contract.validate_python(
        {**variant, "dateOfMeasure": "2026-10-30T15:25:42Z"}
    )
    assert type(model) is generic_model_class
    assert isinstance(model, model_class)
    assert contract.validate_json(contract.dump_json(model)) == model
    assert contract.json_schema()["discriminator"] == {
        "propertyName": "type",
        "mapping": {
            "heart_rate": "#/$defs/HeartRateMeasurementWithType",
            "sleep": "#/$defs/SleepMeasurementWithType",
            "activity": "#/$defs/ActivityMeasurementWithType",
            "blood_pressure": "#/$defs/BloodPressureMeasurementWithType",
        },
    }


@pytest.mark.parametrize(
    "model_class,values",
    [
        (schemas.HeartRateMeasurement, {"bpm": 72}),
        (schemas.SleepMeasurement, {"duration_minutes": 420}),
        (schemas.ActivityMeasurement, {"steps": 1000}),
        (
            schemas.BloodPressureMeasurement,
            {"systolic": 120, "diastolic": 80},
        ),
    ],
)
def test_concrete_measurement_schemas_omit_and_reject_type(model_class, values):
    values = {**values, "dateOfMeasure": "2026-10-30T15:25:42Z"}

    measurement = model_class.model_validate(values)

    assert "type" not in model_class.model_fields
    assert "type" not in model_class.model_json_schema()["properties"]
    assert "type" not in measurement.model_dump()
    with pytest.raises(ValidationError):
        model_class.model_validate({**values, "type": "heart_rate"})


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
    assert set(payload) == {"items", "links", "total"}
    assert payload["total"] == 1
    assert payload["links"]["first"]["href"].endswith("limit=50&offset=0")
    assert payload["links"]["last"]["href"].endswith("limit=50&offset=0")
    assert list_response.headers["x-count"] == "1"
    assert list_response.headers["x-total-count"] == "1"


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
    assert response.status_code == 206, response.text
    body = response.json()
    assert len(body["items"]) == 2
    assert [item["bpm"] for item in body["items"]] == [71, 72]
    assert body["total"] == 5
    assert set(body) == {"items", "links", "total"}
    assert body["links"]["next"]["rel"] == "next"
    assert "limit=2&offset=3" in body["links"]["next"]["href"]
    assert body["links"]["prev"]["rel"] == "prev"
    assert "limit=2&offset=0" in body["links"]["prev"]["href"]
    assert "limit=2&offset=0" in body["links"]["first"]["href"]
    assert "limit=2&offset=4" in body["links"]["last"]["href"]
    assert response.headers["x-count"] == "2"
    assert response.headers["x-total-count"] == "5"
    assert (
        "<" + body["links"]["prev"]["href"] + '>; rel="prev"'
        in response.headers["link"]
    )
    assert (
        "<" + body["links"]["next"]["href"] + '>; rel="next"'
        in response.headers["link"]
    )


@pytest.mark.parametrize(
    "query",
    [
        "limit=abc",
        "limit=1.5",
        "limit=0",
        "limit=-1",
        "offset=not-an-integer",
        "offset=-1",
    ],
)
def test_measurement_pagination_rejects_invalid_values_with_bad_request(client, query):
    response = client.get(f"/subjects/invalid-pagination/measurements?{query}")

    assert response.status_code == 400


def test_measurement_limit_defaults_to_50_and_caps_at_configured_maximum(
    monkeypatch, api_database_environment
):
    monkeypatch.setenv("PHYSIOTRACK_MEASUREMENTS_MAX_LIMIT", "2")
    subject_id = "configured-measurement-limit"
    with TestClient(create_app()) as client:
        for idx in range(3):
            response = client.post(
                f"/subjects/{subject_id}/measurements",
                json={
                    "type": "heart_rate",
                    "bpm": 70 + idx,
                    "dateOfMeasure": f"2026-09-13T12:0{idx}:00Z",
                },
            )
            assert response.status_code == 201, response.text

    with TestClient(create_app()) as client:
        default_response = client.get(f"/subjects/{subject_id}/measurements")
        capped_response = client.get(f"/subjects/{subject_id}/measurements?limit=10")

    assert default_response.status_code == 206
    assert "limit=2&offset=0" in default_response.json()["links"]["first"]["href"]
    assert capped_response.status_code == 206
    assert len(capped_response.json()["items"]) == 2
    assert capped_response.json()["links"]["next"]["href"].endswith("limit=2&offset=2")
    assert "limit=2&offset=2" in capped_response.headers["link"]


@pytest.mark.parametrize("measurement_type,payload", SUPPORTED_MEASUREMENTS)
def test_typed_measurement_routes_dispatch_supported_types(
    client, measurement_type, payload
):
    subject_id = f"typed-{measurement_type}"
    resource_name = plural_resource_name(schemas.MeasurementType(measurement_type))
    typed_payload = {key: value for key, value in payload.items() if key != "type"}

    create_response = client.post(
        f"/subjects/{subject_id}/{resource_name}/", json=typed_payload
    )

    assert create_response.status_code == 201, create_response.text
    created = create_response.json()
    assert "type" not in created
    assert created["subject_id"] == subject_id
    assert create_response.headers["location"] == (
        f"/subjects/{subject_id}/{resource_name}/{created['id']}"
    )
    for alias in (resource_name, measurement_type):
        detail = client.get(f"/subjects/{subject_id}/{alias}/{created['id']}")
        assert detail.status_code == 200, detail.text
        assert detail.json() == created

    list_response = client.get(f"/subjects/{subject_id}/{resource_name}/")

    assert list_response.status_code == 200, list_response.text
    body = list_response.json()
    assert [item["id"] for item in body["items"]] == [created["id"]]
    assert "type" not in body["items"][0]
    assert body["total"] == 1
    assert body["links"]["prev"] is None
    assert body["links"]["next"] is None
    assert body["links"]["first"]["href"].endswith("limit=50&offset=0")
    assert body["links"]["last"]["href"].endswith("limit=50&offset=0")


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
    payload = {
        key: value
        for key, value in SUPPORTED_MEASUREMENTS[-1][1].items()
        if key != "type"
    }

    create_response = client.post(
        f"/subjects/{subject_id}/blood_pressure/", json=payload
    )
    list_response = client.get(f"/subjects/{subject_id}/blood_pressure")

    assert create_response.status_code == 201, create_response.text
    assert list_response.status_code == 200, list_response.text
    assert list_response.json()["items"][0]["id"] == create_response.json()["id"]


def test_typed_measurement_creation_keeps_measurements_path_compatible(client):
    subject_id = "typed-legacy-path"
    payload = {
        key: value
        for key, value in SUPPORTED_MEASUREMENTS[-1][1].items()
        if key != "type"
    }

    create_response = client.post(
        f"/subjects/{subject_id}/measurements/blood_pressure", json=payload
    )

    assert create_response.status_code == 201, create_response.text
    assert "type" not in create_response.json()


def test_typed_measurement_routes_reject_a_body_discriminator(client):
    response = client.post(
        "/subjects/typed-discriminator/heart_rates",
        json={
            "type": "heart_rate",
            "bpm": 72,
            "dateOfMeasure": "2026-09-13T12:00:00Z",
        },
    )

    assert response.status_code == 422


def test_openapi_distinguishes_typed_and_generic_measurement_contracts(client):
    openapi = client.get("/openapi.json").json()
    paths = openapi["paths"]
    schemas_by_name = openapi["components"]["schemas"]

    typed_path = paths["/subjects/{subject_id}/activities"]
    create_schema_ref = typed_path["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"]["$ref"]
    create_schema_name = create_schema_ref.rsplit("/", 1)[-1]
    assert "type" not in schemas_by_name[create_schema_name]["properties"]

    list_schema_ref = typed_path["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]["$ref"]
    list_schema_name = list_schema_ref.rsplit("/", 1)[-1]
    item_schema_ref = schemas_by_name[list_schema_name]["properties"]["items"]["items"][
        "$ref"
    ]
    item_schema_name = item_schema_ref.rsplit("/", 1)[-1]
    assert "type" not in schemas_by_name[item_schema_name]["properties"]

    generic_path = paths["/subjects/{subject_id}/measurements"]
    generic_schema_ref = generic_path["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"]
    assert generic_schema_ref["discriminator"]["propertyName"] == "type"
    generic_union_ref = generic_schema_ref["oneOf"][0]["$ref"]
    generic_union_name = generic_union_ref.rsplit("/", 1)[-1]
    assert "type" in schemas_by_name[generic_union_name]["properties"]

    generic_list_ref = generic_path["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]["$ref"]
    generic_list_name = generic_list_ref.rsplit("/", 1)[-1]
    generic_items_schema = schemas_by_name[generic_list_name]["properties"]["items"][
        "items"
    ]
    assert generic_items_schema["discriminator"]["propertyName"] == "type"

    detail_schema = paths["/subjects/{subject_id}/activities/{measure_id}"]["get"][
        "responses"
    ]["200"]["content"]["application/json"]["schema"]
    assert detail_schema["$ref"] == item_schema_ref
    assert "/subjects/{subject_id}/measurements/{measurement_id}" not in paths


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


def test_measurement_detail_is_scoped_to_subject_and_type(client):
    subject_id = "single-measurement"
    create_response = client.post(
        f"/subjects/{subject_id}/measurements",
        json=SUPPORTED_MEASUREMENTS[0][1],
    )
    assert create_response.status_code == 201, create_response.text
    measurement_id = create_response.json()["id"]

    expected_location = f"/subjects/{subject_id}/heart_rates/{measurement_id}"
    assert create_response.headers["location"] == expected_location
    response = client.get(expected_location)
    assert response.status_code == 200, response.text
    assert response.json()["id"] == measurement_id
    assert "type" not in response.json()

    for url in (
        f"/subjects/other-subject/heart_rates/{measurement_id}",
        f"/subjects/{subject_id}/sleeps/{measurement_id}",
        f"/subjects/{subject_id}/heart_rates/not-a-uuid",
        f"/subjects/{subject_id}/measurements/heart_rates/{measurement_id}",
    ):
        assert client.get(url).status_code == 404

    legacy = client.get(f"/subjects/{subject_id}/measurements/{measurement_id}")
    assert legacy.status_code == 405


def test_measurement_persists_after_api_restarts(api_database_environment):
    subject_id = "persisted-subject"
    payload = {
        key: value
        for key, value in SUPPORTED_MEASUREMENTS[-1][1].items()
        if key != "type"
    }
    with TestClient(create_app()) as writer:
        create_response = writer.post(
            f"/subjects/{subject_id}/measurements/blood_pressures",
            json=payload,
        )
        assert create_response.status_code == 201, create_response.text
        measurement_id = create_response.json()["id"]

    with TestClient(create_app()) as reader:
        response = reader.get(
            f"/subjects/{subject_id}/blood_pressures/{measurement_id}"
        )

    assert response.status_code == 200, response.text
    assert response.json()["id"] == measurement_id


def test_database_configuration_requires_explicit_apphost_fields():
    with pytest.raises(DatabaseConfigurationError, match="required database settings"):
        DatabaseSettings.from_environment({})


def test_measurement_pagination_limit_configuration_defaults_and_validates():
    assert max_measurement_limit_from_environment({}) == 200
    assert (
        max_measurement_limit_from_environment(
            {"PHYSIOTRACK_MEASUREMENTS_MAX_LIMIT": "25"}
        )
        == 25
    )
    for invalid_value in ("", "0", "-1", "invalid"):
        with pytest.raises(MeasurementPaginationConfigurationError):
            max_measurement_limit_from_environment(
                {"PHYSIOTRACK_MEASUREMENTS_MAX_LIMIT": invalid_value}
            )
