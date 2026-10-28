import os
import subprocess
import sys
from pathlib import Path
from shutil import copy2, copytree
from zipfile import ZipFile

import pytest
from alembic import command
from alembic.script import ScriptDirectory

from physiotrack_migrator import cli, runner


@pytest.fixture
def source_checkout(tmp_path, monkeypatch):
    project = Path(runner.__file__).resolve().parents[2]
    checkout = tmp_path / "migrator"
    copytree(project / "src", checkout / "src", ignore=lambda *_: {"__pycache__"})
    (checkout / "pyproject.toml").write_bytes((project / "pyproject.toml").read_bytes())
    copy2(project / "uv.lock", checkout / "uv.lock")
    monkeypatch.setattr(
        runner, "__file__", str(checkout / "src/physiotrack_migrator/runner.py")
    )
    monkeypatch.delenv("PHYSIOTRACK_MIGRATOR_DATABASE_URL", raising=False)
    monkeypatch.delenv("PHYSIOTRACK_MIGRATOR_DATABASE_NAME", raising=False)
    monkeypatch.setenv("UV_NO_SYNC", "1")
    monkeypatch.setenv(
        "UV_PROJECT_ENVIRONMENT", str(Path(sys.executable).parent.parent)
    )
    monkeypatch.setenv("PYTHONPATH", str(checkout / "src"))

    def forbidden(*args, **kwargs):
        pytest.fail("Local revision editing must not access the database.")

    monkeypatch.setattr(runner, "create_engine", forbidden)
    monkeypatch.setattr(cli.Settings, "from_environ", forbidden)
    return checkout / "src/physiotrack_migrator/migrations"


def test_create_delete_round_trip_without_database(source_checkout, capsys):
    versions = source_checkout / "versions"
    before = {path.name: path.read_bytes() for path in versions.glob("*.py")}
    message = "add patient's measurements"
    assert cli.main(["create", "--message", message]) == 0
    scripts = ScriptDirectory(str(source_checkout))
    head = scripts.get_revision(scripts.get_current_head())
    assert head.revision != "0001_measurements"
    assert head.down_revision == "0001_measurements"
    assert head.doc == message
    assert head.module.upgrade() is None
    assert head.module.downgrade() is None
    assert cli.main(["delete"]) == 0
    assert {path.name: path.read_bytes() for path in versions.glob("*.py")} == before
    assert "deleted" in capsys.readouterr().out.lower()


@pytest.mark.parametrize("message", ["", " ", "\t\n"])
def test_create_rejects_blank_message(source_checkout, message, capsys):
    versions = source_checkout / "versions"
    before = set(versions.glob("*.py"))
    assert cli.main(["create", "-m", message]) == 2
    assert "required" in capsys.readouterr().err
    assert set(versions.glob("*.py")) == before


def test_create_requires_message(source_checkout):
    with pytest.raises(SystemExit) as raised:
        cli.main(["create"])
    assert raised.value.code == 2
    assert len(list((source_checkout / "versions").glob("*.py"))) == 1


@pytest.mark.parametrize("action", ["create", "delete"])
def test_revision_editing_requires_source_checkout(
    source_checkout, monkeypatch, action, capsys
):
    monkeypatch.setattr(runner, "__file__", str(source_checkout.parent / "runner.py"))
    (source_checkout.parents[2] / "pyproject.toml").unlink()
    args = [action, "-m", "new revision"] if action == "create" else [action]
    assert cli.main(args) == 2
    assert "source checkout" in capsys.readouterr().err


def test_delete_protects_initial_revision(source_checkout, capsys):
    initial = source_checkout / "versions/0001_measurements.py"
    before = initial.read_bytes()
    assert cli.main(["delete"]) == 2
    assert "initial migration is protected" in capsys.readouterr().err
    assert initial.read_bytes() == before


def test_delete_uses_graph_not_file_time(source_checkout):
    assert cli.main(["create", "-m", "first change"]) == 0
    scripts = ScriptDirectory(str(source_checkout))
    first = Path(scripts.get_revision(scripts.get_current_head()).path)
    assert cli.main(["create", "-m", "second change"]) == 0
    scripts = ScriptDirectory(str(source_checkout))
    second = Path(scripts.get_revision(scripts.get_current_head()).path)
    os.utime(first, (2000000000, 2000000000))
    os.utime(second, (1000000000, 1000000000))
    assert cli.main(["delete"]) == 0
    assert first.is_file()
    assert not second.exists()


@pytest.mark.parametrize(
    "graph", ["empty", "multihead", "merge", "multiple_bases", "broken"]
)
@pytest.mark.parametrize("action", ["create", "delete"])
def test_revision_editing_rejects_ambiguous_graph(
    source_checkout, graph, action, capsys
):
    config = runner.migration_config()
    if graph == "empty":
        (source_checkout / "versions/0001_measurements.py").unlink()
    elif graph == "broken":
        initial = source_checkout / "versions/0001_measurements.py"
        initial.write_text(
            initial.read_text().replace(
                "down_revision = None", 'down_revision = "missing"'
            )
        )
    else:
        command.revision(config, message="first branch")
        command.revision(
            config,
            message="second branch",
            head="base" if graph == "multiple_bases" else "0001_measurements",
            splice=True,
        )
        if graph == "merge":
            command.merge(config, revisions="heads", message="merge branches")
    before = {
        path.name: path.read_bytes()
        for path in (source_checkout / "versions").glob("*.py")
    }
    args = [action, "-m", "new revision"] if action == "create" else [action]
    assert cli.main(args) == 2
    error = capsys.readouterr().err
    assert any(word in error for word in ("chain", "graph"))
    assert {
        path.name: path.read_bytes()
        for path in (source_checkout / "versions").glob("*.py")
    } == before


@pytest.mark.parametrize("symlink_directory", ["file", "versions", "migrations"])
def test_delete_rejects_files_outside_versions(
    source_checkout, tmp_path, symlink_directory, capsys
):
    assert cli.main(["create", "-m", "new revision"]) == 0
    scripts = ScriptDirectory(str(source_checkout))
    head = Path(scripts.get_revision(scripts.get_current_head()).path)
    outside = tmp_path / "outside"
    if symlink_directory == "migrations":
        source_checkout.rename(outside)
        source_checkout.symlink_to(outside, target_is_directory=True)
    elif symlink_directory == "versions":
        (source_checkout / "versions").rename(outside)
        (source_checkout / "versions").symlink_to(outside, target_is_directory=True)
    else:
        outside.write_bytes(head.read_bytes())
        head.unlink()
        head.symlink_to(outside)
    assert cli.main(["delete"]) == 2
    assert "versions directory" in capsys.readouterr().err
    assert outside.exists()
    assert head.exists()


@pytest.mark.parametrize(
    "message",
    [
        "add patient measurements",
        "add patient's measurements",
        "--message starting with dashes",
        'quotes """ and \\ backslash\nsecond line',
        '$(touch shell-marker); `touch shell-marker`; " ; touch shell-marker; #',
        "$(shell touch make-marker)",
    ],
)
def test_make_create_delete_preserves_message(source_checkout, message, monkeypatch):
    root = Path(__file__).resolve().parents[2]
    working = source_checkout.parents[3]
    copy2(root / "Makefile", working / "Makefile")
    monkeypatch.setenv("PATH", f"{Path(sys.executable).parent}:{os.environ['PATH']}")
    before = {
        path.name: path.read_bytes()
        for path in (source_checkout / "versions").glob("*.py")
    }
    result = subprocess.run(
        [
            "make",
            "--no-print-directory",
            "migrate-create",
            "VERSION=0.1.0",
            "BRANCH=test",
            f"NAME={message}",
        ],
        cwd=working,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    scripts = ScriptDirectory(str(source_checkout))
    head = scripts.get_revision(scripts.get_current_head())
    assert head.module.__doc__ == message
    assert head.down_revision == "0001_measurements"
    assert not (working / "shell-marker").exists()
    assert not (working / "make-marker").exists()
    result = subprocess.run(
        [
            "make",
            "--no-print-directory",
            "migrate-delete",
            "VERSION=0.1.0",
            "BRANCH=test",
        ],
        cwd=working,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert {
        path.name: path.read_bytes()
        for path in (source_checkout / "versions").glob("*.py")
    } == before


@pytest.mark.parametrize("name_argument", [[], ["NAME="], ["NAME=   "]])
def test_make_create_requires_name(source_checkout, name_argument, monkeypatch):
    working = source_checkout.parents[3]
    copy2(Path(__file__).resolve().parents[2] / "Makefile", working / "Makefile")
    monkeypatch.setenv("PATH", f"{Path(sys.executable).parent}:{os.environ['PATH']}")
    monkeypatch.delenv("NAME", raising=False)
    result = subprocess.run(
        [
            "make",
            "--no-print-directory",
            "migrate-create",
            "VERSION=0.1.0",
            "BRANCH=test",
            *name_argument,
        ],
        cwd=working,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode != 0
    assert "required" in result.stderr
    assert len(list((source_checkout / "versions").glob("*.py"))) == 1


def test_wheel_contains_working_template_and_refuses_source_editing(
    source_checkout, tmp_path
):
    checkout = source_checkout.parents[2]
    result = subprocess.run(
        [
            "uv",
            "build",
            "--wheel",
            "--offline",
            "--out-dir",
            str(tmp_path / "dist"),
            str(checkout),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    installed = tmp_path / "site-packages"
    with ZipFile(next((tmp_path / "dist").glob("*.whl"))) as wheel:
        assert "physiotrack_migrator/migrations/script.py.mako" in wheel.namelist()
        wheel.extractall(installed)
    script = """
from alembic import command
from alembic.script import ScriptDirectory
from physiotrack_migrator import cli, runner

def forbidden(*args, **kwargs):
    raise AssertionError('Database access is forbidden')

runner.create_engine = forbidden
cli.Settings.from_environ = forbidden
assert cli.main(['create', '-m', 'not in a wheel']) == 2
assert cli.main(['delete']) == 2
config = runner.migration_config()
command.revision(config, message='packaged template')
scripts = ScriptDirectory.from_config(config)
head = scripts.get_revision(scripts.get_current_head())
assert head.down_revision == '0001_measurements'
assert head.module.__doc__ == 'packaged template'
assert head.module.upgrade() is None
assert head.module.downgrade() is None
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(installed)},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_missing_config_cli(monkeypatch, capsys):
    monkeypatch.delenv("PHYSIOTRACK_MIGRATOR_DATABASE_URL", raising=False)
    monkeypatch.delenv("PHYSIOTRACK_MIGRATOR_DATABASE_NAME", raising=False)
    monkeypatch.setenv("DATABASE_URL", "synthetic-secret")
    assert cli.main(["up"]) == 2
    assert "required" in capsys.readouterr().err


def test_database_failure_is_redacted(monkeypatch, capsys):
    monkeypatch.setenv(
        "PHYSIOTRACK_MIGRATOR_DATABASE_URL",
        "postgresql+psycopg://user:synthetic-secret@localhost/physio_test",
    )
    monkeypatch.setenv("PHYSIOTRACK_MIGRATOR_DATABASE_NAME", "physio_test")

    def fail(*args):
        raise RuntimeError("synthetic-secret raw driver message")

    monkeypatch.setattr(cli, "migrate", fail)
    assert cli.main(["up"]) == 1
    captured = capsys.readouterr()
    assert "synthetic-secret" not in captured.err + captured.out
    assert "Traceback" not in captured.err


@pytest.mark.parametrize(
    "args",
    [
        ["unknown-synthetic-secret"],
        ["up", "--revision"],
        ["status", "--revision", "synthetic-secret"],
    ],
)
def test_invalid_arguments_are_redacted(args, capsys):
    with pytest.raises(SystemExit) as raised:
        cli.main(args)
    assert raised.value.code == 2
    assert "synthetic-secret" not in capsys.readouterr().err


def test_entrypoint_has_no_api_dependency():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import physiotrack_migrator.cli; import sys; assert not {'fastapi', 'main', 'features'} & sys.modules.keys()",
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_down_help_warns_about_data_loss(capsys):
    with pytest.raises(SystemExit) as raised:
        cli.main(["down", "--help"])
    assert raised.value.code == 0
    assert "Destructive" in capsys.readouterr().out
