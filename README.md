# PhysioTrack

PhysioTrack is a Python API for recording and tracking physiological data (e.g. heart
rate, sleep, activity), with each measurement scoped to a caller-provided subject
identifier.

## Features

### Implemented

- `GET /health` — API health check, returns status and timestamp
- Subject-scoped measurement creation, retrieval, filtering, and pagination

Measurement routes use resource names derived from the supported variants in
`MeasurementType`: `heart_rates`, `sleeps`, `activities`, and
`blood_pressures`. Canonical singular values such as `blood_pressure` remain
valid aliases.

```text
POST /subjects/{subject_id}/{measurement_resource}
POST /subjects/{subject_id}/measurements/{measurement_resource}
GET  /subjects/{subject_id}/{measurement_resource}/
GET  /subjects/{subject_id}/measurements/{measurement_id}
GET  /subjects/{subject_id}/measurements?type={measurement_type}&limit={n}&offset={n}
```

The legacy `POST /subjects/{subject_id}/measurements` and collection `GET`
remain available. Typed routes validate the body against the URL type's
measurement schema; their request and response bodies omit `type`. The generic
collection routes retain the `type` discriminator because they accept or
return multiple measurement types. Unsupported types such as `heights` are
rejected until their measurement schemas are implemented. Collection responses
include `items`, `total`, and pagination `links`.
Measurements are persisted in the dedicated PostgreSQL database through the
existing migrator ORM models. API startup requires
`PHYSIOTRACK_DATABASE_HOST`, `PHYSIOTRACK_DATABASE_PORT`,
`PHYSIOTRACK_DATABASE_NAME`, `PHYSIOTRACK_DATABASE_USERNAME` (the
`physiotrack_api` role), and `PHYSIOTRACK_DATABASE_PASSWORD`. The API does not
load `.env` files, supply defaults, or run migrations; it fails startup if the
required connection is unavailable. The MedEasy AppHost supplies these fields
after its migrator completes.

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
    measurements/              # Measurement API, service, and schemas
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

Measurement API integration tests and migrator tests use disposable
`postgres:17.6-bookworm` containers with generated test credentials; Docker is
required. They do not use or inspect developer database configuration.

Each target wraps the underlying `uv` commands (e.g. `make sync` runs `uv sync`
and `uv sync --project migrator --frozen`, `make run` runs
`uv run uvicorn main:app --reload --app-dir src`, `make test` runs `uv run pytest`).
You can still invoke `uv` directly if you need more control.

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for a detailed history of changes.

## Standalone schema migrations

The standalone [migrator](migrator/README.md) manages only the schema of the
dedicated PostgreSQL database. `make migrate-up` can provision its restricted
migration role and the API's restricted `physiotrack_api` role when the
bootstrap settings are configured. Migrations do not start an API or create a
database. The API uses the dedicated role and never runs migrations itself.

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
`upgrade`/`downgrade` placeholders, without autogeneration; migration changes
remain explicitly authored and reviewed. Both `migrate-create` and
`migrate-delete` require a source checkout and **do not require database
configuration or connect to a database**.

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
them without loss when IDs remain globally unique. Revision
`0003_measurement_creation_order` adds server-generated creation timestamps for
stable API collection ordering. See the migrator guide for the safety checks
and limitations. The migrator has its own lockfile, tests and non-server Docker
image; its ORM models are also used by the API persistence service.
