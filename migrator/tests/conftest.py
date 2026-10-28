import os
import subprocess
import time
from dataclasses import dataclass
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.pool import NullPool


@dataclass
class Database:
    url: URL
    admin_url: URL

    @property
    def environ(self):
        return {
            **os.environ,
            "PHYSIOTRACK_MIGRATOR_DATABASE_URL": self.url.render_as_string(
                hide_password=False
            ),
            "PHYSIOTRACK_MIGRATOR_DATABASE_NAME": self.url.database,
        }


def docker(*args):
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, timeout=120, check=True
    ).stdout.strip()


def connect(url, **kwargs):
    return psycopg.connect(
        host=url.host,
        port=url.port,
        dbname=url.database,
        user=url.username,
        password=url.password,
        connect_timeout=2,
        **kwargs,
    )


@pytest.fixture(scope="session")
def postgres():
    name = f"physiotrack-migrator-test-{uuid4().hex}"
    password = uuid4().hex
    try:
        docker(
            "run",
            "--detach",
            "--rm",
            "--name",
            name,
            "--publish",
            "127.0.0.1::5432",
            "--tmpfs",
            "/var/lib/postgresql/data:rw",
            "--env",
            f"POSTGRES_PASSWORD={password}",
            "postgres:17.6-bookworm",
        )
        port = int(docker("port", name, "5432/tcp").rsplit(":", 1)[1])
        admin = URL.create(
            "postgresql+psycopg", "postgres", password, "127.0.0.1", port, "postgres"
        )
        deadline = time.monotonic() + 45
        while True:
            try:
                with connect(admin, autocommit=True) as connection:
                    connection.execute(
                        sql.SQL(
                            "CREATE ROLE migrator LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE"
                        ).format(sql.Literal(password))
                    )
                    connection.execute(
                        "REVOKE CONNECT ON DATABASE postgres, template1 FROM PUBLIC"
                    )
                break
            except psycopg.OperationalError:
                if time.monotonic() >= deadline:
                    pytest.fail(
                        "Disposable PostgreSQL did not become ready within 45 seconds."
                    )
                time.sleep(0.2)
        yield admin
    finally:
        subprocess.run(
            ["docker", "rm", "--force", "--volumes", name],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )


@pytest.fixture
def database(postgres):
    name = f"physiotrack_test_{uuid4().hex}"
    with connect(postgres, autocommit=True) as connection:
        connection.execute(
            sql.SQL("CREATE DATABASE {} OWNER migrator").format(sql.Identifier(name))
        )
        connection.execute(
            sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(
                sql.Identifier(name)
            )
        )
    database = Database(
        url=postgres.set(username="migrator", database=name),
        admin_url=postgres.set(database=name),
    )
    try:
        yield database
    finally:
        with connect(postgres, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name))
            )


@pytest.fixture
def engine(database):
    engine = create_engine(database.url, poolclass=NullPool, hide_parameters=True)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(scope="session")
def migrator_image():
    from pathlib import Path

    image = f"physiotrack-migrator-test-{uuid4().hex}"
    try:
        docker("build", "--tag", image, str(Path(__file__).resolve().parents[1]))
        yield image
    finally:
        subprocess.run(
            ["docker", "image", "rm", "--force", image],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
