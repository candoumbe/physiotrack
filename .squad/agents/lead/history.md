# Lead — History

## 2026-09-11 — Équipe créée

- Projet : physiotrack, API Python (FastAPI + uv) de tracking de données physiologiques
- Demandé par : Cyrille NDOUMBE
- État initial : endpoint `/health` en place, packaging migré vers `uv`

## 2026-09-11 — Architecture endpoint mesures physiologiques

- Proposé : schéma Pydantic à union discriminée par `type` (HeartRate/Sleep/Activity), `subject_id`
  en path param, ID mesure via `uuid4`, endpoint unique `POST /subjects/{subject_id}/measurements`,
  stockage in-memory derrière une interface `MeasurementRepository`.
- Skeleton créé : `src/schemas/measurement.py`.
- Décision documentée dans `.squad/decisions.md`. Suite : Backend Dev, Data Engineer, Security, Tester.

## 2026-09-11 — Vertical slice reorganization

- New directives applied: English going forward, vertical slice architecture.
- Restructured `src/` into `src/features/{health,measurements}/`; removed old
  `src/routers/` and `src/schemas/` folders; updated `src/main.py` import.
- `uv run pytest` passed after migration.
- Decision recorded in inbox: `lead-vertical-slice-architecture.md`.

## 2026-09-11 — CHANGELOG.md created

- Created `CHANGELOG.md` at repo root using Keep a Changelog + SemVer format,
  Conventional Commits phrasing, populated from project history.
- `uv run pytest` passed (1 passed).

## 2026-09-11 — README.md created

- Created `README.md` at repo root: project purpose, implemented vs designed
  features, tech stack, project structure, getting-started commands, and a
  pointer to `CHANGELOG.md`.
