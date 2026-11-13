import pytest

from physiotrack_migrator.config import (
    API_ROLE,
    ConfigurationError,
    ProvisioningSettings,
    Settings,
)


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
    assert settings.runtime_url.drivername == "postgresql+psycopg"
    assert "synthetic-secret" not in repr(settings)


def test_native_postgresql_server_url_uses_explicit_database_and_psycopg_driver():
    settings = Settings.from_environ(
        configured("postgresql://migrator:synthetic-secret@localhost:5432")
    )
    assert settings.runtime_url.drivername == "postgresql+psycopg"
    assert settings.runtime_url.database == "physio_test"


def test_bootstrap_and_runtime_uris_are_separate_and_redacted():
    runtime = Settings.from_environ(configured())
    bootstrap_url = "postgresql+psycopg://postgres:admin-secret@localhost/physio_test"
    migrator_password = "migrator-secret-credential-long-enough-32"
    provisioning = ProvisioningSettings.from_environ(
        {
            **configured(),
            "PHYSIOTRACK_MIGRATOR_BOOTSTRAP_DATABASE_URL": bootstrap_url,
            "PHYSIOTRACK_MIGRATOR_PASSWORD": migrator_password,
        }
    )
    assert runtime.runtime_url.username == "migrator"
    assert provisioning.bootstrap_url.username == "postgres"
    assert provisioning.bootstrap_url.password == "admin-secret"
    assert provisioning.migrator_password == migrator_password
    assert "admin-secret" not in repr(provisioning)
    assert migrator_password not in repr(provisioning)


def test_bootstrap_configuration_matches_migrator_runtime_target():
    migrator_password = "migrator-secret-credential-long-enough-32"
    provisioning = ProvisioningSettings.from_environ(
        {
            "PHYSIOTRACK_MIGRATOR_BOOTSTRAP_DATABASE_URL": "postgresql+psycopg://postgres:admin-secret@localhost/physio_test",
            "PHYSIOTRACK_MIGRATOR_DATABASE_NAME": "physio_test",
            "PHYSIOTRACK_MIGRATOR_PASSWORD": migrator_password,
        }
    )
    runtime = Settings.from_environ(
        configured(
            "postgresql+psycopg://physiotrack_migrator:migrator-secret-credential-long-enough-32@localhost/physio_test"
        )
    )

    provisioning.validate_runtime(runtime)


def test_separate_fields_preserve_special_characters_and_hide_secrets():
    values = {
        "PHYSIOTRACK_MIGRATOR_HOST": "localhost",
        "PHYSIOTRACK_MIGRATOR_PORT": "5432",
        "PHYSIOTRACK_MIGRATOR_DATABASE_NAME": "physio_test",
        "PHYSIOTRACK_MIGRATOR_BOOTSTRAP_USERNAME": "postgres",
        "PHYSIOTRACK_MIGRATOR_BOOTSTRAP_PASSWORD": "bootstrap:@/long-secret",
        "PHYSIOTRACK_MIGRATOR_PASSWORD": "migrator:@/" + "m" * 32,
        "PHYSIOTRACK_API_PASSWORD": "api:@/" + "a" * 32,
    }
    settings = Settings.from_environ(values)
    provisioning = ProvisioningSettings.from_environ(values)
    provisioning.validate_runtime(settings)
    assert settings.runtime_url.password == values["PHYSIOTRACK_MIGRATOR_PASSWORD"]
    assert (
        provisioning.bootstrap_url.password
        == values["PHYSIOTRACK_MIGRATOR_BOOTSTRAP_PASSWORD"]
    )
    assert provisioning.api_password == values["PHYSIOTRACK_API_PASSWORD"]
    assert API_ROLE != settings.runtime_url.username
    assert all(
        value not in repr(provisioning)
        for key, value in values.items()
        if "PASSWORD" in key
    )


@pytest.mark.parametrize("api_password", ["short", "m" * 32, "b" * 32])
def test_api_secret_must_be_long_and_distinct(api_password):
    with pytest.raises(ConfigurationError):
        ProvisioningSettings.from_environ(
            {
                "PHYSIOTRACK_MIGRATOR_DATABASE_NAME": "physio_test",
                "PHYSIOTRACK_MIGRATOR_BOOTSTRAP_DATABASE_URL": f"postgresql://postgres:{'b' * 32}@localhost/physio_test",
                "PHYSIOTRACK_MIGRATOR_PASSWORD": "m" * 32,
                "PHYSIOTRACK_API_PASSWORD": api_password,
            }
        )


@pytest.mark.parametrize(
    "runtime_url,runtime_name",
    [
        (
            "postgresql+psycopg://physiotrack_migrator:migrator-secret-credential-long-enough-32@other/physio_test",
            "physio_test",
        ),
        (
            "postgresql+psycopg://physiotrack_migrator:wrong-secret-credential-long-enough-32@localhost/physio_test",
            "physio_test",
        ),
        (
            "postgresql+psycopg://other_role:migrator-secret-credential-long-enough-32@localhost/physio_test",
            "physio_test",
        ),
        (
            "postgresql+psycopg://physiotrack_migrator:migrator-secret-credential-long-enough-32@localhost/physio_other",
            "physio_other",
        ),
    ],
)
def test_bootstrap_configuration_rejects_mismatched_runtime(runtime_url, runtime_name):
    provisioning = ProvisioningSettings.from_environ(
        {
            "PHYSIOTRACK_MIGRATOR_BOOTSTRAP_DATABASE_URL": "postgresql+psycopg://postgres:admin-secret@localhost/physio_test",
            "PHYSIOTRACK_MIGRATOR_DATABASE_NAME": "physio_test",
            "PHYSIOTRACK_MIGRATOR_PASSWORD": "migrator-secret-credential-long-enough-32",
        }
    )
    runtime = Settings.from_environ(
        {
            "PHYSIOTRACK_MIGRATOR_DATABASE_URL": runtime_url,
            "PHYSIOTRACK_MIGRATOR_DATABASE_NAME": runtime_name,
        }
    )

    with pytest.raises(ConfigurationError, match="same dedicated database"):
        provisioning.validate_runtime(runtime)


@pytest.mark.parametrize(
    "values",
    [
        {},
        {"DATABASE_URL": "postgresql://shared"},
        {"PHYSIOTRACK_MIGRATOR_DATABASE_NAME": "physio_test"},
        configured("invalid-synthetic-secret"),
        configured("sqlite:///physio_test"),
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
