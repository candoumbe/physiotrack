"""Explicit, dedicated database configuration with redacted failures."""

import os
from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError

MIGRATOR_ROLE = "physiotrack_migrator"


class ConfigurationError(ValueError):
    pass


@dataclass(frozen=True, repr=False)
class Settings:
    runtime_url: URL
    database_name: str

    @classmethod
    def from_environ(cls, environ: Mapping[str, str] | None = None) -> Settings:
        values = os.environ if environ is None else environ
        raw_url = values.get("PHYSIOTRACK_MIGRATOR_DATABASE_URL", "")
        name = values.get("PHYSIOTRACK_MIGRATOR_DATABASE_NAME", "")
        if not raw_url or not name or name != name.strip():
            raise ConfigurationError(
                "Dedicated migrator URL and database name are required."
            )
        try:
            url = make_url(raw_url)
            if url.drivername == "postgresql":
                url = url.set(drivername="postgresql+psycopg")
            if not url.database:
                url = url.set(database=name)
            valid = (
                url.drivername == "postgresql+psycopg"
                and bool(url.host)
                and bool(url.username)
                and url.password is not None
                and bool(url.database)
                and url.database == name
                and name.casefold() not in {"postgres", "template0", "template1"}
                and (url.port is None or 1 <= url.port <= 65535)
                and set(url.query) <= {"sslmode"}
                and url.query.get("sslmode", "prefer")
                in {"disable", "allow", "prefer", "require", "verify-ca", "verify-full"}
            )
        except ArgumentError, ValueError, TypeError:
            valid = False
        if not valid:
            raise ConfigurationError(
                "Invalid dedicated PostgreSQL target configuration."
            )
        return cls(runtime_url=url, database_name=name)


@dataclass(frozen=True, repr=False)
class ProvisioningSettings:
    bootstrap_url: URL
    database_name: str
    migrator_password: str

    @classmethod
    def from_environ(
        cls, environ: Mapping[str, str] | None = None
    ) -> ProvisioningSettings:
        values = os.environ if environ is None else environ
        raw_url = values.get("PHYSIOTRACK_MIGRATOR_BOOTSTRAP_DATABASE_URL", "")
        name = values.get("PHYSIOTRACK_MIGRATOR_DATABASE_NAME", "")
        password = values.get("PHYSIOTRACK_MIGRATOR_PASSWORD", "")
        if not raw_url or not name or name != name.strip() or len(password) < 32:
            raise ConfigurationError(
                "Dedicated provisioning target and migrator credential are required."
            )
        try:
            url = make_url(raw_url)
            if url.drivername == "postgresql":
                url = url.set(drivername="postgresql+psycopg")
            valid = (
                url.drivername == "postgresql+psycopg"
                and bool(url.host)
                and bool(url.username)
                and url.username != "physiotrack_migrator"
                and url.password is not None
                and url.database == name
                and name.casefold() not in {"postgres", "template0", "template1"}
                and (url.port is None or 1 <= url.port <= 65535)
                and set(url.query) <= {"sslmode"}
                and url.query.get("sslmode", "prefer")
                in {"disable", "allow", "prefer", "require", "verify-ca", "verify-full"}
            )
        except ArgumentError, ValueError, TypeError:
            valid = False
        if not valid:
            raise ConfigurationError("Invalid dedicated provisioning configuration.")
        return cls(bootstrap_url=url, database_name=name, migrator_password=password)

    def validate_runtime(self, settings: Settings) -> None:
        runtime_url = settings.runtime_url
        if (
            runtime_url.username != MIGRATOR_ROLE
            or runtime_url.password != self.migrator_password
            or runtime_url.host.casefold() != self.bootstrap_url.host.casefold()
            or (runtime_url.port or 5432) != (self.bootstrap_url.port or 5432)
            or runtime_url.database != self.bootstrap_url.database
            or settings.database_name != self.database_name
        ):
            raise ConfigurationError(
                "Bootstrap and migration settings must target the same dedicated database and migrator credential."
            )
