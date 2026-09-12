# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
### 🚀 New features

#### API

- Added `GET /health` endpoint returning API status and timestamp

### 📝 Documentation

- Documented architecture for physiological measurement recording API (subject-scoped
  measurements, discriminated-union schema, generic `POST`/`GET` endpoints)
- Added Pydantic schema skeleton for measurements (common base schema + heart rate,
  sleep and activity types)

### 🧪 Tests

- Added `test/test_health.py` covering the health endpoint

### 🧹 Housekeeping

- Migrated package management from pip to uv (`pyproject.toml`, `uv.lock`)
- Reorganized project code to follow vertical slice architecture (`src/features/health`,
  `src/features/measurements`)
- Added a `Makefile` wrapping common project tasks (`install`, `run`, `test`, `lint`,
  `format`, `clean`, `help`), and added `ruff` as a dev dependency to back the `lint`
  and `format` targets

[Unreleased]: https://github.com/candoumbe/physiotrack/commits/HEAD
