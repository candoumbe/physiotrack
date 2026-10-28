"""Explicit, dedicated database configuration with redacted failures."""

import os
from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError


class ConfigurationError(ValueError):
    pass


@dataclass(frozen=True, repr=False)
class Settings:
    url: URL
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
        return cls(url=url, database_name=name)
