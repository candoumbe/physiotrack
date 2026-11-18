# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
### 🚀 New features

#### Schema migrations

- Added an independently installable Python >=3.14 PostgreSQL schema migrator
  with locked Alembic, SQLAlchemy Core and Psycopg dependencies, `up`/`down`/`status`
  commands, dedicated target validation, transactional rollback, a separate
  non-root Docker image and disposable PostgreSQL contract tests.
- Added migration `0003_measurement_creation_order` with server-generated
  creation timestamps for stable measurement ordering across types and API restarts.
- Added migration `0004_subject_id_uuid` converting `subject_id` to the `uuid` type.
  It refuses to run when existing rows contain a non-UUID `subject_id`.

#### API

- Changed `subject_id` and `measure_id` path parameters to UUIDs; malformed values
  now return `422` (previously `404` for `measure_id`).
- Changed `limit` and `offset` query parameters to integers validated by FastAPI
  (`limit >= 1`, `offset >= 0`); invalid values now return `422` instead of `400`.

- Added `GET /health` endpoint returning API status and timestamp
- Standardized HTTP error responses as RFC 7807 Problem Details with the
  `application/problem+json` media type, including validation, routing, explicit
  API, and sanitized internal server errors
- Added subject-scoped measurement endpoints: `POST /subjects/{subject_id}/measurements` creates a measurement and `GET /subjects/{subject_id}/measurements` lists measurements for a subject
- Added measurement list filtering by `type`, offset-based pagination with `limit` and `offset`, and `next`/`previous` pagination links
- Added generic typed creation and collection routes, including
  `POST /subjects/{subject_id}/measurements/blood_pressures` and
  `GET /subjects/{subject_id}/blood_pressures/`. Supported resource names are
  derived from registered measurement schemas without endpoint changes;
  singular aliases and existing measurement routes remain available.
- Rejected unsupported measurement types and creation payloads whose type
  does not match the URL.
- Centralized measurement creation and reads in a PostgreSQL-backed service
  using the migrator ORM models, replacing in-memory storage.
- Required explicit database configuration and connection validation at startup,
  using the restricted `physiotrack_api` role without running migrations or
  falling back to in-memory storage. Storage availability errors return
  sanitized HTTP 503 Problem Details.
- feat(telemetry): added OpenTelemetry support for API instrumentation — tracing, metrics
  and log correlation via FastAPI auto-instrumentation, configured entirely through
  standard `OTEL_*` environment variables (Aspire-injected, no hardcoded endpoint)

### 📝 Documentation

- Documented architecture for physiological measurement recording API (subject-scoped
  measurements, discriminated-union schema, generic `POST`/`GET` endpoints)
- Added Pydantic schema skeleton for measurements (common base schema + heart rate,
  sleep and activity types)
- Extended measurement schemas with type-specific values and blood pressure measurements
- Documented generic resource routes, PostgreSQL connection settings, migration
  prerequisites, and Docker requirements for database integration tests.

### 🧪 Tests

- Added `test/test_health.py` covering the health endpoint
- Added focused Problem Details coverage for validation, conflict, not-found,
  method-not-allowed, and unexpected server errors
- Added disposable PostgreSQL coverage for measurement persistence, generic
  routes, singular aliases, unsupported types, payload validation, and schema
  registration extensibility; updated migration tests for creation timestamps.

### 🧹 Housekeeping

- Added Makefile Gitflow automation for feature, chore, coldfix, release, and hotfix branch workflows, including validation, versioning, merging, and tagging
- Migrated package management from pip to uv (`pyproject.toml`, `uv.lock`)
- Reorganized project code to follow vertical slice architecture (`src/features/health`,
  `src/features/measurements`)
- Added a `Makefile` wrapping common project tasks (`install`, `run`, `test`, `lint`,
  `format`, `clean`, `help`), and added `ruff` as a dev dependency to back the `lint`
  and `format` targets
- Recorded the offset-based pagination convention for measurement lists
- Included the migrator ORM package and PostgreSQL runtime dependencies in
  the API container image.

[Unreleased]: https://github.com/candoumbe/physiotrack/commits/HEAD
