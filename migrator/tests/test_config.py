import pytest

from physiotrack_migrator.config import ConfigurationError, Settings


def configured(
    url="postgresql+psycopg://migrator:synthetic-secret@localhost/physio_test",
):
    return {
        "PHYSIOTRACK_MIGRATOR_DATABASE_URL": url,
        "PHYSIOTRACK_MIGRATOR_DATABASE_NAME": "physio_test",
    }


def test_dedicated_configuration():
    settings = Settings.from_environ(configured())
    assert settings.database_name == "physio_test"
    assert settings.url.drivername == "postgresql+psycopg"
    assert "synthetic-secret" not in repr(settings)


@pytest.mark.parametrize(
    "values",
    [
        {},
        {"DATABASE_URL": "postgresql://shared"},
        {"PHYSIOTRACK_MIGRATOR_DATABASE_NAME": "physio_test"},
        configured("invalid-synthetic-secret"),
        configured("sqlite:///physio_test"),
        configured("postgresql://migrator:synthetic-secret@localhost/physio_test"),
        configured("postgresql+psycopg://migrator:synthetic-secret@localhost/other"),
        configured(
            "postgresql+psycopg://migrator:synthetic-secret@localhost:bad/physio_test"
        ),
        configured(
            "postgresql+psycopg://migrator:synthetic-secret@localhost:0/physio_test"
        ),
        configured("postgresql+psycopg://migrator@localhost/physio_test"),
        configured("postgresql+psycopg://migrator:synthetic-secret@/physio_test"),
        configured(
            "postgresql+psycopg://migrator:synthetic-secret@localhost/physio_test?host=other"
        ),
        configured(
            "postgresql+psycopg://migrator:synthetic-secret@localhost/physio_test?sslmode=bad"
        ),
        configured(
            "postgresql+psycopg://migrator:synthetic-secret@localhost/physio_test?sslmode=require&sslmode=disable"
        ),
        {**configured(), "PHYSIOTRACK_MIGRATOR_DATABASE_NAME": " physio_test "},
        *[
            {
                "PHYSIOTRACK_MIGRATOR_DATABASE_URL": f"postgresql+psycopg://migrator:synthetic-secret@localhost/{name}",
                "PHYSIOTRACK_MIGRATOR_DATABASE_NAME": name,
            }
            for name in ("postgres", "template0", "template1")
        ],
    ],
)
def test_invalid_configuration_is_redacted(values):
    with pytest.raises(ConfigurationError) as raised:
        Settings.from_environ(values)
    assert "synthetic-secret" not in str(raised.value)
    assert "postgresql" not in str(raised.value)
