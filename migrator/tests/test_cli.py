import subprocess
import sys

import pytest

from physiotrack_migrator import cli


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
