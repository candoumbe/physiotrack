# PhysioTrack

PhysioTrack is a Python API for recording and tracking physiological data (e.g. heart
rate, sleep, activity), with each measurement scoped to a caller-provided subject
identifier.

## Features

### Implemented

- `GET /health` — API health check, returns status and timestamp

### Designed, not yet implemented

The following describes the target architecture for physiological measurement
recording. Only the Pydantic schemas exist today (`src/features/measurements/schemas/`);
no router or endpoints have been implemented yet.

- Subject-scoped measurements, with the subject identifier (`subject_id`) carried in the
  URL path
- System-generated measurement id
- A discriminated-union schema supporting multiple measurement types: heart rate, sleep,
  and activity
- Generic `POST`/`GET` endpoints for recording and retrieving measurements

## Tech stack

- [Python](https://www.python.org/) (>= 3.14)
- [FastAPI](https://fastapi.tiangolo.com/)
- [uv](https://docs.astral.sh/uv/) — package manager
- [pytest](https://docs.pytest.org/) — testing

## Project structure

The codebase follows a vertical slice architecture: each feature lives in its own
self-contained folder under `src/features/{feature}/`, grouping together the router,
schemas, and any other code specific to that feature.

```
src/
  main.py                     # FastAPI app entry point
  features/
    health/                   # GET /health
      router.py
    measurements/              # Physiological measurement schemas (in progress)
      schemas/                 # One class per module; public reexports in __init__.py
```

## Getting started

A `Makefile` wraps the common project tasks. Run `make help` to list all available
targets.

Install API development tools and standalone migrator dependencies into their
separate environments (`.venv` and `migrator/.venv`):

```bash
make sync
```

`make install` is an alias for the same installation. Alembic is included in the
API's `dev` dependency group for local tooling, not in the API runtime image.
The migrator keeps its own dependencies and lockfile.

`uv sync` does not activate the environment or put its commands on your shell's
`PATH`. From the Physiotrack root, run Alembic through uv:

```bash
uv run --frozen alembic --version
uv run --frozen alembic init --help
```

Alternatively, run `source .venv/bin/activate` before using bare `alembic` commands.
For a different, uninitialized project, creating an Alembic environment requires
a target directory: `uv run alembic init <directory>`. **Do not run `alembic init`
in this repository:** the standalone migrator is already initialized. Use the
`migrate-create`, `migrate-delete`, `migrate-up`, `migrate-down` and
`migrate-status` targets below instead.

Run the API:

```bash
make run
```

Run tests:

```bash
make test
```

Each target wraps the underlying `uv` commands (e.g. `make sync` runs `uv sync`
and `uv sync --project migrator --frozen`, `make run` runs
`uv run uvicorn main:app --reload --app-dir src`, `make test` runs `uv run pytest`).
You can still invoke `uv` directly if you need more control.

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for a detailed history of changes.

## Standalone schema migrations

The independent [migrator](migrator/README.md) manages only the schema of a
dedicated PostgreSQL database. `make migrate-up` can provision its restricted
migration role when the optional bootstrap URI is configured. The API remains
**in-memory**; no database configuration is required to run it. Migrations do not
start an API, create a database or enable business persistence.

```bash
uv sync --project migrator --frozen
make migrate-up
make migrate-status
make migrate-down
```

Make shortcuts from the Physiotrack root (also listed by `make help`):

```bash
make migrate-up
make migrate-status
make migrate-down
make migrate-up REVISION=0001_measurements
make migrate-down REVISION=base
make migrate-create NAME="add patient's measurements"
make migrate-delete
```

`migrate-create` requires a nonblank `NAME`, used intact as the Alembic migration
message, not the revision identifier. It generates an empty revision with
`upgrade`/`downgrade` placeholders, without autogeneration (the API has no ORM
metadata). Both `migrate-create` and `migrate-delete` require a source checkout
and **do not require database configuration or connect to a database**.

`migrate-delete` removes only the unique head file of a linear local migration
chain, never the initial revision. It refuses empty or ambiguous graphs and
files outside the source `versions` directory. **Delete is not rollback:** use
it only for a local revision that has not been applied to any database. It cannot
verify that condition without connecting. For an applied revision, roll back
separately with `migrate-down REVISION=<previous-revision>` where operationally
appropriate before considering deletion. Never delete shared/applied history
as a substitute for a new corrective migration.

`REVISION` is optional for `migrate-up` and `migrate-down`; when omitted, the
CLI defaults remain `head` and `base`, respectively. From the MedEasy root,
use `make -C physiotrack <target>`.

For `migrate-up`, `migrate-down` and `migrate-status`, set
`PHYSIOTRACK_MIGRATOR_DATABASE_URL` and `PHYSIOTRACK_MIGRATOR_DATABASE_NAME`;
`migrate-up` also provisions the restricted role first when the optional
`PHYSIOTRACK_MIGRATOR_BOOTSTRAP_DATABASE_URL` and
`PHYSIOTRACK_MIGRATOR_PASSWORD` are set, as described in the migrator guide.
`down` to base is destructive: it removes the four dedicated measurement tables
and their data, never the database. Revision `0002_dedicated_measurements` safely
splits existing measurements by type; rollback to `0001_measurements` merges
them without loss when IDs remain globally unique. See the migrator guide for
the safety checks and limitations. The migrator has its own dependencies, lockfile, tests and
non-server Docker image.
