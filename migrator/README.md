# Physiotrack schema migrator

An independent Python >=3.14 executable for schema migrations only. It uses
Alembic, SQLAlchemy ORM and Psycopg 3. It does not import, install or start
FastAPI or `src/main.py`. The API still stores measurements **in memory**;
running this project does not enable API persistence or transfer any data.

## Dedicated database prerequisite

A database administrator must **pre-provision an empty, dedicated PostgreSQL
database** and a distinct migration role. Give that role access only to this
database and permission to create objects in its `public` schema. The role must
not be a superuser or have `CREATEDB`. Never use an existing Agenda, Documents,
Aspire, shared or production database to try the migrator or its tests.

Database provisioning is separate from schema migration: this executable never
creates or drops databases, never drops schemas, and never uses `CASCADE`.
The expected-name check cannot prove dedication; restricted credentials and
correct provisioning remain mandatory.

Supply both environment variables through your shell or secret manager:

| Variable | Required value |
| --- | --- |
| `PHYSIOTRACK_MIGRATOR_DATABASE_URL` | `postgresql://<role>:<percent-encoded-password>@<host>:5432[/<database>]` or `postgresql+psycopg://...` |
| `PHYSIOTRACK_MIGRATOR_DATABASE_NAME` | Exact, explicit name of the pre-provisioned dedicated database |

There are no defaults, `.env` loading, generic `DATABASE_URL` or API/Aspire
fallbacks. Username, password, host and database must be explicit. Native
`postgresql://` URLs are normalized to the installed `postgresql+psycopg` driver.
If the URL has no database path, the explicit `PHYSIOTRACK_MIGRATOR_DATABASE_NAME`
is applied; if it does, the path must match that name. Explicit
`postgresql+psycopg://` URLs are also accepted. The only optional URL query
parameter is `sslmode` (`disable`, `allow`, `prefer`, `require`, `verify-ca`,
`verify-full`); use certificate verification where appropriate. URL-encode special
characters in credentials. Do not put credentials in command arguments or source
control.

The runner checks `current_database()` before DDL and refuses `postgres`,
`template0`, `template1`, privileged roles, foreign schemas/objects, unmarked
tables and unknown revisions. It checks table ownership and migrator markers
on later runs too. These checks are accident prevention, not a security boundary
against a database owner intentionally forging history or markers.

Connections time out after 5 seconds; statements after 15 seconds and lock waits
after 5 seconds. A transaction-scoped advisory lock rejects concurrent runs.
Driver failures, SQL parameters, URLs and tracebacks are not printed by the CLI.
Exit codes are 0 for success, 2 for invalid configuration/arguments and 1 for
database, ownership or migration failures. `status` never creates schema objects.

## Install and run

From the Physiotrack repository root:

```bash
uv sync --project migrator --frozen
uv run --project migrator --frozen physiotrack-migrator status
uv run --project migrator --frozen physiotrack-migrator up
uv run --project migrator --frozen physiotrack-migrator down
```

Or from this directory, without installing the API:

```bash
uv sync --frozen
uv run --frozen physiotrack-migrator up
uv run --frozen physiotrack-migrator status
uv run --frozen physiotrack-migrator down --revision base
```

From the MedEasy root use `--project physiotrack/migrator`. Once installed, the
console script can run from any working directory; migration files are packaged
with the executable. Use `uv sync --frozen --no-dev` for runtime dependencies only.
The committed lockfile fixes runtime and test dependency versions.

`up` defaults to `head`; `down` defaults to `base`. Both accept `--revision`, for
example `up --revision 0001_measurements`. `status` prints `revision: base` or
the installed revision. Repeating `up` at head or `down` at base is a no-op.
Migrations and their Alembic revision changes are transactional.

**Rollback to base is destructive:** `down` to base drops all owned measurement
tables and **all their rows**. It leaves the database and an empty, marked
`alembic_version` table in place. A later `up` recreates empty tables, not lost data.
Back up data and obtain operational approval before a rollback.
`down --revision 0001_measurements` instead merges the four tables back into the
initial table without deleting measurements, subject to the UUID limitation below.

## Develop local revisions

The existing Alembic environment is configured programmatically by the runner;
do not run `alembic init` or create a second migration directory.
From the Physiotrack root:

```bash
make migrate-create NAME="add patient's measurements"
make migrate-delete
```

Equivalent standalone CLI commands:

```bash
uv run --project migrator --frozen physiotrack-migrator create --message "add patient's measurements"
uv run --project migrator --frozen physiotrack-migrator delete
```

`create` (`-m`/`--message`) requires a nonblank message, preserved as supplied;
`NAME` is not a revision identifier. Alembic generates the revision ID and links
`down_revision` to the current head. Fill in the generated `upgrade` and
`downgrade` placeholders manually: the CLI does not enable autogeneration.
Alembic's environment loads `Base.metadata` from `physiotrack_migrator.models`;
keep that metadata and new revisions in sync.
Quote shell arguments normally; for a literal dollar sign use single quotes or
escape it in your shell. Make passes the message as data, not shell code.

Both commands require a source checkout, refuse installed wheels/site-packages,
and neither read database settings nor connect to a database. `delete` removes
only the head file of a single linear revision chain, irrespective of file
timestamps. The initial revision is protected. Empty histories, multiple heads,
multiple bases, merged/dependent histories and files outside the source
`versions` directory (including symbolic links) are refused. Local validation
errors return exit code 2; filesystem/generation failures return 1.

**Delete is not rollback.** Use it only for a local revision that has not been
applied to any database; no database check is performed or implied. If already
applied, rollback is a separate, potentially destructive operation:
`make migrate-down REVISION=<previous-revision>`. Coordinate it for every
affected database before removing a local file. Do not rewrite shared/applied
history: prefer a new corrective migration. `up`, `down` and `status` still
require both database variables and retain their existing behavior.

## Schema and limits

Revision `0001_measurements` creates `public.measurements` with a supplied UUID
primary key, nullable nonempty `subject_id`, `type`, `date_of_measure` and the
variant-specific columns. Checks allow exactly one of:

| Type | Required columns | Optional columns |
| --- | --- | --- |
| `heart_rate` | `bpm` | none |
| `sleep` | `duration_minutes` | `quality_score` |
| `activity` | `steps` | `calories` |
| `blood_pressure` | `systolic`, `diastolic`, `unit = 'mmHg'` | none |

All columns belonging to other variants must be null. Missing optional columns
remain null in this historical schema.

Revision `0002_dedicated_measurements` (the current head) replaces that table with
four independent tables in `public`: `heart_rate_measurements`,
`sleep_measurements`, `activity_measurements` and `blood_pressure_measurements`.
Each owns `id`, `subject_id`, `date_of_measure` and only its variant-specific
columns from the table above. Required fields are `NOT NULL`; optional fields
remain nullable. The `type` discriminator is no longer stored.

The new revision locks source tables against concurrent writes, copies values
without reserializing dates or converting numbers, and compares every old field
in both directions with `EXCEPT ALL` before dropping source tables. DDL and data
copy share a transaction; mismatches, unexpected columns or name collisions abort
without losing rows. Unknown objects and ownership mismatches remain rejected.
Rollback to `0001_measurements` uses its original DDL and verifies the merged
data before dropping the dedicated tables. IDs must be globally unique for that
rollback: independent tables can contain overlapping UUIDs, but the initial
table cannot. The CLI refuses such a downgrade with an actionable message;
resolve overlapping IDs explicitly before retrying. No IDs are silently changed.
The existing statement/lock timeouts still apply; large datasets may require
an operationally planned migration window. Historical revision `0001` is unchanged.

There is no subject table, foreign key, server-generated UUID, speculative
index or invented medical bound. Integers use unconstrained `NUMERIC` plus finite,
integral checks rather than silently limiting Python integers to `BIGINT`.
PostgreSQL still has a technical limit of 131072 digits before the decimal point;
Python integers are not mathematically bounded this way. The optional float
columns use double precision, including non-finite floats accepted by the current
Pydantic models; no new medical or finite-only validation is invented here.

`date_of_measure` deliberately stores the ISO-8601 datetime representation as
`TEXT`, preserving naive versus timezone-aware input and offsets, without
inventing UTC normalization. **SQL does not enforce datetime syntax**: contract
tests validate Pydantic serialization/round trips, but direct SQL writers could
store invalid date text. Timezone semantics, date indexing/querying and stronger
SQL validation belong to a future persistence design, not this migrator.

## Measurement models

`physiotrack_migrator.models` exposes `Base`, the abstract Python `Measurement`,
and `HeartRateMeasurement`, `SleepMeasurement`, `ActivityMeasurement` and
`BloodPressureMeasurement`. Each concrete class maps its own dedicated table.
`Measurement` only shares Python field and constraint declarations; it has no
table or mapper and cannot be selected. Query the concrete class, for example
`select(HeartRateMeasurement)`. Reconstruct the API discriminator from the chosen
variant when serializing to the unchanged Pydantic contract.

All variants share `id`, `subject_id` and `date_of_measure` (the ORM name for the
API's `dateOfMeasure`). ORM writes default `id` to a new UUID4 and blood pressure
`unit` to `mmHg`; these are client-side defaults, not new database defaults.
Integer fields load as Python `int`, and dates bind/load as `datetime` using the
existing lossless `NUMERIC` and ISO-8601 `TEXT` storage. These models match revision
`0002_dedicated_measurements`; they do not connect the API to the database.

## Separate container

From the Physiotrack root:

```bash
docker build -t physiotrack-migrator:local migrator
docker run --rm --network <dedicated-database-network> \
  --env PHYSIOTRACK_MIGRATOR_DATABASE_URL \
  --env PHYSIOTRACK_MIGRATOR_DATABASE_NAME \
  physiotrack-migrator:local up
```

Use the same command with `status`, `down` or `down --revision base`. The URL host
must be reachable from the selected container network (not the container's own
`localhost`). The image runs as a non-root user, contains only installed runtime
dependencies and packaged migrations, opens no server port and exits after the
command. Its build context excludes virtual environments, secrets and tests.

## Validation

From this directory:

```bash
uv sync --frozen
uv run --frozen pytest
uv run --frozen ruff check .
uv run --frozen ruff format --check .
```

The full suite requires Docker on Linux (host networking for the image smoke
test). It starts its own pinned `postgres:17.6-bookworm` container with tmpfs
storage, random loopback port and synthetic credentials, then provisions only
randomly named test databases and a non-superuser role. It ignores supplied
database configuration. Containers, test databases and the generated application
image are cleaned up in fixture finalizers on success or failure. A forced kill
of the entire test process can interrupt finalizers; leftover resources are named
`physiotrack-migrator-test-*` and must be removed manually in that case.

Tests inspect versions, columns, primary keys and checks through
`up/up/down/down/up`; round-trip the four real Pydantic variants (development-only
imports), null optionals, large/negative integers and naive/aware datetimes;
reject invalid variants/foreign fields, foreign objects, unknown history and
permissions; and inject DDL errors to prove upgrade/downgrade atomicity. A real
connection timeout and synthetic secret sentinels verify bounded, redacted CLI
errors. The separate image test proves non-editable packaging works without the
API source or API dependencies.

For tests without Docker: `uv run --frozen pytest -m 'not integration'`.
From the API root its existing suite remains `uv run --frozen pytest` (or
`make test`); pytest discovery is restricted to `test/` so it does not accidentally
load this project's independent tests or dependencies.