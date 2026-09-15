import sys
from pathlib import Path

from fastapi import HTTPException
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from main import create_app


def _client() -> TestClient:
    app = create_app()

    @app.get("/test/items/{item_id}", include_in_schema=False)
    def get_item(item_id: int) -> dict[str, int]:
        return {"item_id": item_id}

    @app.get("/test/conflict", include_in_schema=False)
    def conflict() -> None:
        raise HTTPException(
            status_code=409,
            detail="Measurement already exists",
            headers={"X-Error-Code": "duplicate-measurement"},
        )

    @app.get("/test/unexpected", include_in_schema=False)
    def unexpected() -> None:
        raise RuntimeError("database password must not leak")

    return TestClient(app, raise_server_exceptions=False)


def _assert_problem(
    response,
    *,
    status: int,
    title: str,
    instance: str,
    type_uri: str = "about:blank",
) -> dict:
    assert response.status_code == status
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["type"] == type_uri
    assert body["title"] == title
    assert body["status"] == status
    assert body["detail"]
    assert body["instance"] == instance
    return body


def test_validation_error_uses_problem_details() -> None:
    response = _client().get("/test/items/not-an-integer")

    body = _assert_problem(
        response,
        status=422,
        title="Request Validation Error",
        instance="/test/items/not-an-integer",
        type_uri="urn:physiotrack:problem:request-validation",
    )
    assert body["errors"][0]["loc"] == ["path", "item_id"]


def test_explicit_http_exception_uses_problem_details() -> None:
    response = _client().get("/test/conflict")

    body = _assert_problem(
        response,
        status=409,
        title="Conflict",
        instance="/test/conflict",
    )
    assert body["detail"] == "Measurement already exists"
    assert response.headers["x-error-code"] == "duplicate-measurement"


def test_route_not_found_uses_problem_details() -> None:
    response = _client().get("/missing?source=client")

    body = _assert_problem(
        response,
        status=404,
        title="Not Found",
        instance="/missing?source=client",
    )
    assert body["detail"] == "Not Found"


def test_method_not_allowed_uses_problem_details() -> None:
    response = _client().post("/health")

    body = _assert_problem(
        response, status=405, title="Method Not Allowed", instance="/health"
    )
    assert body["detail"] == "Method Not Allowed"
    assert response.headers["allow"] == "GET"


def test_unexpected_error_is_sanitized_problem_details() -> None:
    response = _client().get("/test/unexpected")

    body = _assert_problem(
        response,
        status=500,
        title="Internal Server Error",
        instance="/test/unexpected",
    )
    assert body["detail"] == "An unexpected error occurred."
    assert "password" not in response.text
