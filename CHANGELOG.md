# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
### 🚀 New features

#### API

- Added `GET /health` endpoint returning API status and timestamp
- Standardized HTTP error responses as RFC 7807 Problem Details with the
  `application/problem+json` media type, including validation, routing, explicit
  API, and sanitized internal server errors
- Added subject-scoped measurement endpoints: `POST /subjects/{subject_id}/measurements` creates a measurement and `GET /subjects/{subject_id}/measurements` lists measurements for a subject
- Added measurement list filtering by `type`, offset-based pagination with `limit` and `offset`, and `next`/`previous` pagination links

### 📝 Documentation

- Documented architecture for physiological measurement recording API (subject-scoped
  measurements, discriminated-union schema, generic `POST`/`GET` endpoints)
- Added Pydantic schema skeleton for measurements (common base schema + heart rate,
  sleep and activity types)
- Extended measurement schemas with type-specific values and blood pressure measurements

### 🧪 Tests

- Added `test/test_health.py` covering the health endpoint
- Added focused Problem Details coverage for validation, conflict, not-found,
  method-not-allowed, and unexpected server errors

### 🧹 Housekeeping

- Added Makefile Gitflow automation for feature, chore, coldfix, release, and hotfix branch workflows, including validation, versioning, merging, and tagging
- Migrated package management from pip to uv (`pyproject.toml`, `uv.lock`)
- Reorganized project code to follow vertical slice architecture (`src/features/health`,
  `src/features/measurements`)
- Added a `Makefile` wrapping common project tasks (`install`, `run`, `test`, `lint`,
  `format`, `clean`, `help`), and added `ruff` as a dev dependency to back the `lint`
  and `format` targets
- Recorded the offset-based pagination convention for measurement lists

[Unreleased]: https://github.com/candoumbe/physiotrack/commits/HEAD
