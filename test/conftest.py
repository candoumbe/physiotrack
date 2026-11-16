import secrets
import subprocess
import time
from collections.abc import Generator
from dataclasses import dataclass
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from physiotrack_migrator.config import ProvisioningSettings, Settings
from physiotrack_migrator.runner import provision_and_migrate
from psycopg import sql
from sqlalchemy.engine import URL


def _docker(*args: str) -> str:
    return subprocess.run(
        ["docker", *args],
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    ).stdout.strip()


def _connect(url: URL, *, autocommit: bool = False):
    return psycopg.connect(
        host=url.host,
        port=url.port,
        dbname=url.database,
        user=url.username,
        password=url.password,
        connect_timeout=3,
        autocommit=autocommit,
    )


@pytest.fixture(scope="session")
def postgres_server() -> Generator[URL]:
    try:
        _docker("info")
    except OSError, subprocess.SubprocessError:
        pytest.skip("Docker is required for PostgreSQL API integration tests.")

    container_name = f"physiotrack-api-test-{uuid4().hex}"
    admin_password = secrets.token_urlsafe(36)
    try:
        try:
            _docker(
                "run",
                "--detach",
                "--rm",
                "--name",
                container_name,
                "--publish",
                "127.0.0.1::5432",
                "--tmpfs",
                "/var/lib/postgresql/data:rw",
                "--env",
                f"POSTGRES_PASSWORD={admin_password}",
                "postgres:17.6-bookworm",
            )
        except subprocess.CalledProcessError:
            pytest.fail("Could not start disposable PostgreSQL for API tests.")

        port = int(_docker("port", container_name, "5432/tcp").rsplit(":", 1)[1])
        admin_url = URL.create(
            "postgresql+psycopg",
            username="postgres",
            password=admin_password,
            host="127.0.0.1",
            port=port,
            database="postgres",
        )
        deadline = time.monotonic() + 45
        while True:
            try:
                with _connect(admin_url):
                    break
            except psycopg.OperationalError:
                if time.monotonic() >= deadline:
                    pytest.fail("Disposable PostgreSQL did not become ready.")
                time.sleep(0.2)
        yield admin_url
    finally:
        subprocess.run(
            ["docker", "rm", "--force", "--volumes", container_name],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )


@dataclass(frozen=True, repr=False)
class ApiDatabase:
    host: str
    port: int
    name: str
    username: str
    password: str


@pytest.fixture(scope="session")
def api_database(
    postgres_server: URL,
) -> Generator[ApiDatabase]:
    database_name = f"physiotrack_api_test_{uuid4().hex}"
    with _connect(postgres_server, autocommit=True) as connection:
        connection.execute(
            sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name))
        )
        connection.execute(
            sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(
                sql.Identifier(database_name)
            )
        )

    bootstrap_url = postgres_server.set(database=database_name)
    migrator_password = secrets.token_urlsafe(36)
    api_password = secrets.token_urlsafe(36)
    runtime_url = URL.create(
        "postgresql+psycopg",
        username="physiotrack_migrator",
        password=migrator_password,
        host=postgres_server.host,
        port=postgres_server.port,
        database=database_name,
    )
    settings = Settings(runtime_url=runtime_url, database_name=database_name)
    provisioning = ProvisioningSettings(
        bootstrap_url=bootstrap_url,
        database_name=database_name,
        migrator_password=migrator_password,
        api_password=api_password,
    )

    try:
        provision_and_migrate(settings, "head", provisioning)
        yield ApiDatabase(
            host=postgres_server.host,
            port=postgres_server.port,
            name=database_name,
            username="physiotrack_api",
            password=api_password,
        )
    finally:
        with _connect(postgres_server, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(
                    sql.Identifier(database_name)
                )
            )


@pytest.fixture
def api_database_environment(api_database: ApiDatabase, monkeypatch) -> ApiDatabase:
    monkeypatch.setenv("PHYSIOTRACK_DATABASE_HOST", api_database.host)
    monkeypatch.setenv("PHYSIOTRACK_DATABASE_PORT", str(api_database.port))
    monkeypatch.setenv("PHYSIOTRACK_DATABASE_NAME", api_database.name)
    monkeypatch.setenv("PHYSIOTRACK_DATABASE_USERNAME", api_database.username)
    monkeypatch.setenv("PHYSIOTRACK_DATABASE_PASSWORD", api_database.password)
    return api_database


@pytest.fixture
def client(
    api_database_environment: ApiDatabase,
) -> Generator[TestClient]:
    from main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client
