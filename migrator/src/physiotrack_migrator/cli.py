"""Bounded, redacted command-line interface."""

import argparse
import sys
from collections.abc import Sequence

from physiotrack_migrator.config import ConfigurationError, Settings
from physiotrack_migrator.runner import (
    LocalRevisionError,
    TargetError,
    edit_revision,
    migrate,
)


class Parser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "Invalid command or arguments. See --help.\n")


def main(argv: Sequence[str] | None = None) -> int:
    parser = Parser(
        description="Migrate only a pre-provisioned dedicated Physiotrack database."
    )
    commands = parser.add_subparsers(dest="command", required=True, parser_class=Parser)
    up = commands.add_parser("up", help="Apply schema migrations (default: head).")
    up.add_argument(
        "--revision", default="head", help="Target revision (default: head)."
    )
    down = commands.add_parser(
        "down",
        help="Destructive rollback: removes owned tables and their data, never the database.",
        description="Destructive rollback: removes owned tables and their data, never the database.",
    )
    down.add_argument(
        "--revision", default="base", help="Target revision (default: base)."
    )
    commands.add_parser(
        "status", help="Show the current revision without changing the schema."
    )
    create = commands.add_parser(
        "create", help="Create a local empty revision without a database."
    )
    create.add_argument(
        "-m", "--message", required=True, help="Migration message, not revision ID."
    )
    commands.add_parser(
        "delete",
        help="Delete the local unapplied head file only; never roll back the database.",
        description="Delete the local unapplied head file only; never roll back the database.",
    )
    args = parser.parse_args(argv)
    try:
        if args.command in {"create", "delete"}:
            revision = edit_revision(args.command, getattr(args, "message", None))
            print(
                f"{'created' if args.command == 'create' else 'deleted'} revision: {revision}"
            )
            return 0
        settings = Settings.from_environ()
        revision = migrate(settings, args.command, getattr(args, "revision", None))
    except LocalRevisionError as error:
        print(str(error), file=sys.stderr)
        return 2
    except ConfigurationError as error:
        print(str(error), file=sys.stderr)
        return 2
    except TargetError:
        print(
            "Database target rejected: verify dedication, role and migration ownership.",
            file=sys.stderr,
        )
        return 1
    except Exception:
        print(
            "Local revision editing failed: verify source files and permissions."
            if args.command in {"create", "delete"}
            else "Migration failed: verify database availability, permissions and revision.",
            file=sys.stderr,
        )
        return 1
    print(f"revision: {revision}")
    return 0
