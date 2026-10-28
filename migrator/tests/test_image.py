import subprocess
from uuid import uuid4

import pytest
import sqlalchemy as sa

pytestmark = pytest.mark.integration


def run_image(image, database, *args, entrypoint=None):
    name = f"physiotrack-migrator-test-{uuid4().hex}"
    command = ["docker", "run", "--rm", "--name", name, "--network", "host"]
    for key in (
        "PHYSIOTRACK_MIGRATOR_DATABASE_URL",
        "PHYSIOTRACK_MIGRATOR_DATABASE_NAME",
    ):
        command.extend(["--env", key])
    if entrypoint:
        command.extend(["--entrypoint", entrypoint])
    try:
        return subprocess.run(
            [*command, image, *args],
            env=database.environ,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    finally:
        subprocess.run(
            ["docker", "rm", "--force", "--volumes", name],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )


def test_noneditable_runtime_image(migrator_image, database, engine):
    result = run_image(
        migrator_image,
        database,
        "-c",
        "import importlib.util, os, sys; "
        "assert os.getuid() != 0; assert sys.version_info >= (3, 14); "
        "assert all(importlib.util.find_spec(name) is None for name in ('fastapi', 'pydantic', 'main')); "
        "import physiotrack_migrator.cli",
        entrypoint="python",
    )
    assert result.returncode == 0, result.stderr
    for action, expected in [
        ("up", "0001_measurements"),
        ("status", "0001_measurements"),
        ("down", "base"),
    ]:
        result = run_image(migrator_image, database, action)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == f"revision: {expected}"
    assert sa.inspect(engine).get_table_names(schema="public") == ["alembic_version"]
