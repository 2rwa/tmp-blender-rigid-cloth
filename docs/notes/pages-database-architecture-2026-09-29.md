# Pages / experiment index architecture — 2026-09-29

The repository-wide experiment index is no longer generated as one large HTML document.

## Source model

Committed experiment results remain the raw source of truth:

- `experiments/*/experiment.json`
- `experiments52/*/experiment.json`
- `results/*/validation.json`
- optional `results/*/*-report.json`
- result README metadata
- preview / video / blend artifacts

## Relational aggregate

`tools/build_pages.py` updates a persistent SQLite database at:

- `docs/data/experiments.sqlite`

The database is committed with Pages output, so history can survive across later Actions runs.

A root mirror is also generated at:

- `data/experiments.sqlite`
- `data/experiments.json`

The root mirror is convenient for local analysis; the Pages copy is the persistent publication copy.

Core relations:

- `experiments` — experiment identity and current metadata
- `runs` — published run history
- `experiment_configs` — common render / frame configuration
- `cloth_configs` — cloth-specific parameters
- `collider_configs` — collider-specific parameters
- `systems` + `experiment_systems` — many-to-many physics systems
- `tags` + `experiment_tags` — many-to-many descriptive facets
- `metrics` — typed measurements associated with a run
- `artifacts` — preview / video / validation / report / blend files

Raw manifest and validation JSON are retained in the database so schema evolution does not discard unknown fields.

## Web publication model

The browser does **not** query SQLite directly.

Actions exports a denormalized materialized view:

- `docs/data/experiments.json`

The fixed viewer then fetches this JSON.

Static viewer sources:

- `web/index.html`
- `web/app.js`
- `web/style.css`

The builder copies these into `docs/` and only regenerates data / copied assets.

This separates:

1. normalized storage for analysis and history;
2. denormalized JSON for a simple static Pages UI.

## Current UI

The top page supports:

- text search
- category filter
- physics-system filter
- tag filter
- sorting
- experiment/system/category counts
- snapshot-first cards
- click-to-load video
- summary metrics
- expandable parameters
- source / result / Actions / commit links
- direct JSON and SQLite links

This design is intentionally not cloth-specific. New experiment families can be indexed without adding HTML cards manually.

## Extension policy

When a new physics family appears:

- keep its original report/config JSON;
- add a dedicated config relation only when repeated structured comparison becomes useful;
- keep uncommon measurements in `metrics`;
- expose only useful summary fields in the JSON materialized view.

Avoid turning every possible Blender property into a column before it is actually needed.
