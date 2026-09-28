# Pages / experiment index architecture — 2026-09-29

The repository-wide experiment index is no longer generated as one large HTML document.

This document records both the data architecture and the 2026-09-29 top-page migration.

## Why the top page changed

The previous gallery embedded one complete HTML card per experiment into generated `index.html`.

That was workable while the repository had only a few experiments, but it became increasingly awkward because:

- every new result rewrote a large HTML file;
- the page mixed presentation with experiment indexing;
- cloth, rigid-body, soft-body, fluid, and hybrid experiments have different metrics;
- filtering and cross-experiment comparison were difficult to add cleanly;
- the repository is expected to continue accumulating experiment families.

The replacement separates storage, publication data, and presentation.

## Source model

Committed experiment results remain the raw source of truth:

- `experiments/*/experiment.json`
- `experiments52/*/experiment.json`
- `results/*/validation.json`
- optional `results/*/*-report.json`
- result README metadata
- preview / video / blend artifacts

The database is an aggregate/index. It does not replace these source files.

## Relational aggregate

`tools/build_pages.py` updates a persistent SQLite database at:

- `docs/data/experiments.sqlite`

The Pages copy is committed, so run/index history can survive later Actions rebuilds.

A root mirror is generated for local analysis:

- `data/experiments.sqlite`
- `data/experiments.json`

Core relations:

- `experiments` — experiment identity and current metadata
- `runs` — published run history
- `experiment_configs` — common render/frame configuration
- `cloth_configs` — cloth-specific parameters
- `collider_configs` — collider-specific parameters
- `systems` + `experiment_systems` — many-to-many physics systems
- `tags` + `experiment_tags` — many-to-many descriptive facets
- `metrics` — typed measurements associated with a run
- `artifacts` — preview/video/validation/report/blend files

Raw manifest and validation JSON are retained inside the database so schema evolution does not discard fields that are not yet normalized.

The design is intentionally repository-wide rather than cloth-specific.

## Why relations are needed

A single flat table would quickly become sparse and misleading because this repository contains multiple physics families.

Examples already present include:

- cloth
- cloth tearing
- rigid body
- soft body
- cloth + rigid body
- cloth + soft body
- cloth/fluid combinations
- Geometry Nodes experimental dynamics

Different families produce different measurements.

For example:

- tearing: first tear frame, max components, max vertices;
- soft body: max displacement;
- rigid body: body count, solver settings, tunneling observations;
- hybrid systems: multiple subsystem measurements.

Common experiment/run identity therefore lives in normalized tables, while family-specific configuration gets dedicated tables only when repeated structured comparison is useful.

Rare or newly introduced measurements remain in `metrics` and raw JSON.

## Web publication model

The browser does **not** query SQLite directly.

The builder exports a denormalized materialized view:

- `docs/data/experiments.json`

The top page fetches this JSON and renders cards dynamically.

Static viewer sources:

- `web/index.html`
- `web/app.js`
- `web/style.css`

Generated Pages copies:

- `docs/index.html`
- `docs/app.js`
- `docs/style.css`

This gives two intentionally different representations:

1. **SQLite** — normalized storage for analysis/history;
2. **JSON** — denormalized read model for a simple static browser UI.

## Top-page behavior after the migration

The top page now supports:

- text search across id/title/description/tags;
- category filter;
- physics-system filter;
- tag filter;
- newest/oldest/title/category sorting;
- experiment/category/system counts;
- snapshot-first cards;
- click-to-load video instead of loading every MP4 at page startup;
- summary metrics selected per experiment;
- expandable parameters;
- source/result/Actions/commit links;
- direct JSON and SQLite links.

The HTML contains only a reusable card template. Experiment cards are not hard-coded into the page.

At the first successful migration build the index contained:

- **40 experiments**
- **5 categories**
- **5 physics systems**
- **21 tags**

These counts are not constants; they are generated from current committed results.

## Build flow

The current build flow is:

```text
experiments/ + experiments52/
             +
          results/
             |
             v
     tools/build_pages.py
             |
             +--> docs/data/experiments.sqlite
             |
             +--> docs/data/experiments.json
             |
             +--> data/experiments.sqlite
             +--> data/experiments.json
             |
             +--> docs/assets/<experiment>/*
             |
             +--> fixed web viewer -> docs/
```

The builder reconstructs/updates the aggregate from committed results, then exports the Pages read model.

## Result ordering

The index preserves the original gallery behavior of ordering by **first publication time**, not by latest rerun.

Re-running an old experiment should not make it appear to be a newly created experiment.

The first-add commit time of the result README is used as the stable publication-order key when available.

## UI asset policy

The viewer initially loads preview images only.

MP4 is loaded only when the play button is clicked.

This avoids loading many videos just because the repository has accumulated many experiments.

Pages copies only the public browser-facing assets needed by the UI:

- preview
- validation JSON
- MP4 when present

Large `.blend` files remain linked through GitHub rather than copied into the Pages asset directory.

## Actions integration

The dedicated workflow is:

- `.github/workflows/pages-gallery.yml`

Relevant triggers include changes to:

- `tools/build_pages.py`
- `web/**`
- the workflow itself

The Pages workflow builds the DB/JSON/viewer, commits generated output when needed, and deploys `docs/`.

Push races are handled by rebuilding from latest `main` before a retry.

The concurrency group uses latest-build preference so obsolete duplicate gallery rebuilds do not pile up.

## Important workflow isolation lesson

During the migration, changing `web/**` unintentionally triggered the general Blender 4 experiment workflow because those paths were not yet ignored.

The Blender workflow was then updated to ignore:

- `web/**`
- `data/**`

Top-page or index-only changes must not launch expensive physics simulations.

If a new generated/index directory is added later, review workflow path filters so presentation-only changes stay isolated from simulation workflows.

## Failure observed during migration

Two Pages rebuilds briefly overlapped because both the main feature commit and a trigger commit started the gallery workflow.

The later duplicate build hit a normal non-fast-forward push rejection.

This was not a data-generation failure.

The fix was to make the Pages publishing step race-safe:

1. attempt push;
2. if rejected, fetch latest main;
3. reset/rebuild the index from latest main;
4. commit only if output still differs;
5. push again.

This same pattern should be retained for generated repository output.

## How to add a new experiment family

Do not edit the top-page HTML to add cards.

Instead:

1. add/maintain the experiment manifest;
2. publish a result containing `validation.json` and preview;
3. preserve richer report/config JSON when available;
4. let `tools/build_pages.py` index it;
5. add a dedicated relational config table only if that family develops repeated comparable parameters.

If basic inference cannot classify the new family well, extend category/system/tag inference in the builder rather than adding special-case HTML.

## How to change the top page

Presentation changes should normally touch:

- `web/index.html`
- `web/app.js`
- `web/style.css`

Then let the Pages workflow regenerate `docs/`.

Do **not** manually edit generated experiment cards in `docs/index.html`.

For data-model changes, modify:

- `tools/build_pages.py`

and, when needed, increment the SQLite/JSON schema version.

## Extension policy

When a new physics family appears:

- keep its original report/config JSON;
- add a dedicated config relation only when repeated structured comparison becomes useful;
- keep uncommon measurements in `metrics`;
- expose only useful summary fields in the JSON materialized view.

Avoid turning every possible Blender property into a column before it is actually needed.

## Public page

GitHub Pages:

- https://2rwa.github.io/tmp-blender-rigid-cloth/

The public top page should be treated as a database-backed experiment browser, not as a hand-maintained gallery.
