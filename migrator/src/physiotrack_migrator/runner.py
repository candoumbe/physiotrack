"""Transactional Alembic execution against a checked, isolated target."""

import base64
import hashlib
import hmac
import secrets
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from alembic.script.revision import RevisionError
from alembic.util import CommandError
from psycopg import sql
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.pool import NullPool

from physiotrack_migrator.config import (
    MIGRATOR_ROLE,
    ProvisioningSettings,
    Settings,
)

OWNER_MARKER = "physiotrack-migrator"
MEASUREMENT_TABLES = {
    "heart_rate_measurements",
    "sleep_measurements",
    "activity_measurements",
    "blood_pressure_measurements",
}


class TargetError(RuntimeError):
    pass


class ProvisioningError(RuntimeError):
    pass


class LocalRevisionError(RuntimeError):
    pass


def migration_config() -> Config:
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
    return config


def edit_revision(action: str, message: str | None = None) -> str:
    if action not in {"create", "delete"}:
        raise ValueError("Unsupported local revision action.")
    if action == "create" and (message is None or not message.strip()):
        raise LocalRevisionError("NAME / --message is required and must not be blank.")
    package = Path(__file__).absolute().parent
    if (
        package.parent.name != "src"
        or not (package.parents[1] / "pyproject.toml").is_file()
    ):
        raise LocalRevisionError(
            "Revision editing requires a source checkout, not an installed wheel."
        )
    config = migration_config()
    scripts = ScriptDirectory.from_config(config)
    versions = package / "migrations" / "versions"
    if (
        Path(scripts.dir).resolve() != (package / "migrations").resolve()
        or (package / "migrations").is_symlink()
        or versions.is_symlink()
        or any(path.is_symlink() for path in versions.glob("*.py"))
    ):
        raise LocalRevisionError(
            "Revision files must stay inside the source versions directory."
        )
    try:
        heads = scripts.get_heads()
        revisions = list(scripts.walk_revisions())
        if (
            len(heads) != 1
            or len(scripts.get_bases()) != 1
            or any(
                isinstance(item.down_revision, tuple) or item.dependencies
                for item in revisions
            )
        ):
            raise LocalRevisionError(
                "Expected one unambiguous linear migration chain and a unique head."
            )
        head = scripts.get_revision(heads[0])
        if action == "create":
            created = command.revision(config, message=message, autogenerate=False)
            return created.revision
        if head.down_revision is None:
            raise LocalRevisionError(
                "No deletable revision: the initial migration is protected."
            )
        path = Path(head.path)
        if (
            path.is_symlink()
            or path.resolve().parent != versions.resolve()
            or path.suffix != ".py"
        ):
            raise LocalRevisionError(
                "Refusing to delete a file outside the source versions directory."
            )
        path.unlink()
        return head.revision
    except (CommandError, RevisionError, KeyError) as error:
        raise LocalRevisionError(
            "Invalid or ambiguous Alembic revision graph."
        ) from error


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
            name not in {"measurements", "alembic_version", *MEASUREMENT_TABLES}
            or kind != "r"
            or owner != user
            or marker != OWNER_MARKER
            for name, kind, owner, marker in relations
        )
    ):
        raise TargetError()
    tables = {row[0] for row in relations}
    if tables - {"alembic_version"} and "alembic_version" not in tables:
        raise TargetError()
    revisions = MigrationContext.configure(
        connection, opts={"version_table_schema": "public"}
    ).get_current_heads()
    if (
        len(revisions) > 1
        or any(revision not in known_revisions for revision in revisions)
        or tables - {"alembic_version"}
        != (
            set()
            if not revisions
            else {"measurements"}
            if revisions == ("0001_measurements",)
            else MEASUREMENT_TABLES
        )
    ):
        raise TargetError()


def _scram_verifier(password: str) -> str:
    salt = secrets.token_bytes(16)
    salted_password = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, 4096
    )
    client_key = hmac.new(salted_password, b"Client Key", hashlib.sha256).digest()
    stored_key = hashlib.sha256(client_key).digest()
    server_key = hmac.new(salted_password, b"Server Key", hashlib.sha256).digest()
    encode = lambda value: base64.b64encode(value).decode("ascii")
    return (
        f"SCRAM-SHA-256$4096:{encode(salt)}${encode(stored_key)}:{encode(server_key)}"
    )


def _execute_composed(connection: Connection, statement: sql.Composable) -> None:
    driver_connection = connection.connection.driver_connection
    connection.exec_driver_sql(statement.as_string(driver_connection))


def provision(settings: ProvisioningSettings) -> None:
    engine = create_engine(
        settings.bootstrap_url,
        poolclass=NullPool,
        hide_parameters=True,
        connect_args={
            "connect_timeout": 5,
            "application_name": "physiotrack-migrator-bootstrap",
        },
    )
    try:
        with engine.begin() as connection:
            actual_name, current_user = connection.execute(
                text("SELECT current_database(), current_user")
            ).one()
            if actual_name != settings.database_name or current_user == MIGRATOR_ROLE:
                raise ProvisioningError()

            schema_owner = connection.scalar(
                text(
                    "SELECT pg_get_userbyid(nspowner) FROM pg_namespace "
                    "WHERE nspname = 'public'"
                )
            )
            if schema_owner not in {current_user, "pg_database_owner", MIGRATOR_ROLE}:
                raise ProvisioningError()

            has_foreign_owner = connection.scalar(
                text(
                    "SELECT EXISTS (SELECT 1 FROM pg_class c "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = 'public' AND c.relkind NOT IN ('i', 'I', 't') "
                    "AND pg_get_userbyid(c.relowner) <> :role)"
                ),
                {"role": MIGRATOR_ROLE},
            )
            if has_foreign_owner:
                raise ProvisioningError()

            role_exists = connection.scalar(
                text("SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :role)"),
                {"role": MIGRATOR_ROLE},
            )
            if role_exists:
                memberships = connection.execute(
                    text(
                        "SELECT granted.rolname, member.rolname FROM pg_auth_members m "
                        "JOIN pg_roles granted ON granted.oid = m.roleid "
                        "JOIN pg_roles member ON member.oid = m.member "
                        "WHERE granted.rolname = :role OR member.rolname = :role"
                    ),
                    {"role": MIGRATOR_ROLE},
                ).all()
                for granted_role, member_role in memberships:
                    revoked_role = (
                        MIGRATOR_ROLE if granted_role == MIGRATOR_ROLE else granted_role
                    )
                    revoked_member = (
                        member_role if granted_role == MIGRATOR_ROLE else MIGRATOR_ROLE
                    )
                    _execute_composed(
                        connection,
                        sql.SQL("REVOKE {} FROM {}").format(
                            sql.Identifier(revoked_role), sql.Identifier(revoked_member)
                        ),
                    )

            role_statement = sql.SQL(
                "{} ROLE {} WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                "NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD {}"
            ).format(
                sql.SQL("ALTER") if role_exists else sql.SQL("CREATE"),
                sql.Identifier(MIGRATOR_ROLE),
                sql.Literal(_scram_verifier(settings.migrator_password)),
            )
            _execute_composed(connection, role_statement)

            _execute_composed(
                connection,
                sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                    sql.Identifier(settings.database_name),
                    sql.Identifier(MIGRATOR_ROLE),
                ),
            )
            _execute_composed(
                connection,
                sql.SQL("ALTER SCHEMA public OWNER TO {}").format(
                    sql.Identifier(MIGRATOR_ROLE)
                ),
            )
            _execute_composed(
                connection,
                sql.SQL("GRANT USAGE, CREATE ON SCHEMA public TO {}").format(
                    sql.Identifier(MIGRATOR_ROLE)
                ),
            )
    except ProvisioningError:
        raise
    except Exception as error:
        raise ProvisioningError() from error
    finally:
        engine.dispose()


def migrate(settings: Settings, action: str, revision: str | None = None) -> str:
    config = migration_config()
    scripts = ScriptDirectory.from_config(config)
    known_revisions = {migration.revision for migration in scripts.walk_revisions()}
    if action not in {"up", "down", "status"}:
        raise ValueError("Unsupported migration action.")
    if action != "status":
        scripts.get_revision(revision)
    engine = create_engine(
        settings.runtime_url,
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


def provision_and_migrate(
    settings: Settings, revision: str, provisioning: ProvisioningSettings
) -> str:
    provisioning.validate_runtime(settings)
    provision(provisioning)
    return migrate(settings, "up", revision)
