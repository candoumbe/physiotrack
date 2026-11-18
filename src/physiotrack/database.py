from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import SQLAlchemyError


class DatabaseConfigurationError(RuntimeError):
    """The required dedicated Physiotrack database configuration is invalid."""


class DatabaseUnavailable(RuntimeError):
    """The configured Physiotrack database could not be reached or used."""


@dataclass(frozen=True, repr=False)
class DatabaseSettings:
    url: URL

    @classmethod
    def from_environment(
        cls, environ: Mapping[str, str] | None = None
    ) -> DatabaseSettings:
        values = os.environ if environ is None else environ
        required = (
            "PHYSIOTRACK_DATABASE_HOST",
            "PHYSIOTRACK_DATABASE_PORT",
            "PHYSIOTRACK_DATABASE_NAME",
            "PHYSIOTRACK_DATABASE_USERNAME",
            "PHYSIOTRACK_DATABASE_PASSWORD",
        )
        missing = [name for name in required if not values.get(name)]
        if missing:
            raise DatabaseConfigurationError(
                f"Missing required database settings: {', '.join(missing)}"
            )

        database_name = values["PHYSIOTRACK_DATABASE_NAME"]
        username = values["PHYSIOTRACK_DATABASE_USERNAME"]
        if (
            database_name.casefold() in {"postgres", "template0", "template1"}
            or username != "physiotrack_api"
        ):
            raise DatabaseConfigurationError(
                "The API must use its dedicated Physiotrack database and role."
            )

        try:
            port = int(values["PHYSIOTRACK_DATABASE_PORT"])
            if not 1 <= port <= 65535:
                raise ValueError
            url = URL.create(
                "postgresql+psycopg",
                username=username,
                password=values["PHYSIOTRACK_DATABASE_PASSWORD"],
                host=values["PHYSIOTRACK_DATABASE_HOST"],
                port=port,
                database=database_name,
            )
        except ValueError, TypeError:
            raise DatabaseConfigurationError(
                "Invalid Physiotrack database connection settings."
            ) from None

        return cls(url=url)


def create_database_engine(settings: DatabaseSettings) -> Engine:
    return create_engine(
        settings.url,
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args={
            "connect_timeout": 5,
            "application_name": "physiotrack-api",
        },
    )


def verify_database_connection(engine: Engine) -> None:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        engine.dispose()
        raise DatabaseUnavailable(
            "The configured Physiotrack database is unavailable."
        ) from None
