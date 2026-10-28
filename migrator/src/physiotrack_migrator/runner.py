"""Transactional Alembic execution against a checked, isolated target."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.pool import NullPool

from physiotrack_migrator.config import Settings

OWNER_MARKER = "physiotrack-migrator"


class TargetError(RuntimeError):
    pass


def checked_target(
    connection: Connection, settings: Settings, known_revisions: set[str]
) -> None:
    actual_name, privileged = connection.execute(
        text(
            "SELECT current_database(), rolsuper OR rolcreatedb "
            "FROM pg_roles WHERE rolname = current_user"
        )
    ).one()
    if actual_name != settings.database_name or privileged:
        raise TargetError()
    if not connection.scalar(text("SELECT pg_try_advisory_xact_lock(716284903104)")):
        raise TargetError()
    namespaces = connection.scalars(
        text(
            "SELECT nspname FROM pg_namespace WHERE nspname NOT IN ('public', 'information_schema') "
            "AND left(nspname, 3) <> 'pg_'"
        )
    ).all()
    foreign_objects = connection.scalar(
        text(
            "SELECT EXISTS (SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'public') OR EXISTS ("
            "SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace "
            "WHERE n.nspname = 'public' AND t.typtype IN ('e', 'd')) OR EXISTS ("
            "SELECT 1 FROM pg_extension WHERE extname <> 'plpgsql')"
        )
    )
    relations = connection.execute(
        text(
            "SELECT c.relname, c.relkind, pg_get_userbyid(c.relowner), "
            "obj_description(c.oid, 'pg_class') FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relkind NOT IN ('i', 'I', 't')"
        )
    ).all()
    user = connection.scalar(text("SELECT current_user"))
    if (
        namespaces
        or foreign_objects
        or any(
            name not in {"measurements", "alembic_version"}
            or kind != "r"
            or owner != user
            or marker != OWNER_MARKER
            for name, kind, owner, marker in relations
        )
    ):
        raise TargetError()
    tables = {row[0] for row in relations}
    if "measurements" in tables and "alembic_version" not in tables:
        raise TargetError()
    revisions = MigrationContext.configure(
        connection, opts={"version_table_schema": "public"}
    ).get_current_heads()
    if (
        len(revisions) > 1
        or any(revision not in known_revisions for revision in revisions)
        or (bool(revisions) != ("measurements" in tables))
    ):
        raise TargetError()


def migrate(settings: Settings, action: str, revision: str | None = None) -> str:
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
    scripts = ScriptDirectory.from_config(config)
    known_revisions = {migration.revision for migration in scripts.walk_revisions()}
    if action not in {"up", "down", "status"}:
        raise ValueError("Unsupported migration action.")
    if action != "status":
        scripts.get_revision(revision)
    engine = create_engine(
        settings.url,
        poolclass=NullPool,
        hide_parameters=True,
        connect_args={
            "connect_timeout": 5,
            "application_name": "physiotrack-migrator",
            "options": "-c statement_timeout=15000 -c lock_timeout=5000 -c search_path=public",
        },
    )
    try:
        with engine.begin() as connection:
            checked_target(connection, settings, known_revisions)
            if action != "status":
                config.attributes["connection"] = connection
                if action == "up":
                    command.upgrade(config, revision)
                else:
                    command.downgrade(config, revision)
                connection.execute(
                    text(
                        "COMMENT ON TABLE public.alembic_version IS 'physiotrack-migrator'"
                    )
                )
            revisions = MigrationContext.configure(
                connection, opts={"version_table_schema": "public"}
            ).get_current_heads()
            return revisions[0] if revisions else "base"
    finally:
        engine.dispose()
