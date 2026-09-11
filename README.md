# PhysioTrack

PhysioTrack is a Python API for recording and tracking physiological data (e.g. heart
rate, sleep, activity), with each measurement scoped to a caller-provided subject
identifier.

## Features

### Implemented

- `GET /health` — API health check, returns status and timestamp

### Designed, not yet implemented

The following describes the target architecture for physiological measurement
recording. Only the Pydantic schemas exist today (`src/features/measurements/schemas.py`);
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
      schemas.py
```

## Getting started

Install dependencies:

```bash
uv sync
```

Run the API:

```bash
uv run uvicorn main:app --reload --app-dir src
```

Run tests:

```bash
uv run pytest
```

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for a detailed history of changes.
