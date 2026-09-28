# tmp-blender-rigid-cloth

Public Blender sandbox focused on rigid-body, cloth, collision, soft-body, fluid, and combined physics experiments.

This repository is split out from [2rwa/tmp-blender](https://github.com/2rwa/tmp-blender) so physics-heavy experiments can evolve independently without carrying every Blender experiment with them.

## Baseline

The initial checkpoint is `experiments/cloth-hammock-rigidbody-drop-eevee/`, copied from the known-good Cloth + Rigid Body experiment in `tmp-blender`.

- Blender 4.0.2
- 480×360 / 24 fps / 192 frames / 8 seconds
- cloth grid 45×35
- cloth self-collision enabled
- 12 active rigid-body spheres
- hidden passive rigid-body proxy
- wind + turbulence
- animated camera
- headless-safe sequential simulation bake

The important headless pattern is preserved: cloth deformation is baked to shape keys, while evaluated rigid-body transforms are baked to ordinary object keyframes. The workflow avoids `bpy.ops.rigidbody.bake_to_keyframes()`, which failed under headless Actions context.

The repository also contains a separate Blender 5.2.2 experimental Geometry Nodes Cloth Dynamics / Tearing line.

## Repository layout

- `.github/workflows/blender-experiment.yml` — Blender 4 simulation/render/publish pipeline
- `.github/workflows/blender52-tearing.yml` — Blender 5.2 minimal tearing pipeline
- `.github/workflows/blender52-impact-batch.yml` — Blender 5.2 impact/tearing batch pipeline
- `.github/workflows/pages-gallery.yml` — experiment index / Pages build and deployment
- `tools/experiment.py` — discovery, planning, validation, publishing helpers
- `tools/build_pages.py` — result indexer, SQLite updater, JSON exporter, Pages builder
- `experiments/` — Blender 4 experiment source
- `experiments52/` — Blender 5.2 experiment source
- `results/` — generated persistent experiment outputs
- `data/` — root SQLite/JSON index mirrors for analysis
- `web/` — fixed top-page viewer source
- `docs/` — GitHub Pages output and persistent published index DB
- `docs/notes/START-HERE.md` — current continuation notes

## Development workflow

1. Inspect and reuse existing experiments and tools first.
2. Run cheap Python/static checks before Blender simulation or rendering.
3. Use GitHub Actions for long tests.
4. Preserve failures that are useful physics observations instead of hiding them.
5. Validate the actual movie/result, not only process exit status.
6. Keep presentation-only changes isolated from physics workflows.
7. For generated repository output, rebuild from latest main if a push races with another writer.

Timeouts vary by workflow. The current Blender 5.2 impact/tearing batch uses a **180-minute heavy-job upper bound** and supports up to **10 parallel render cases**. Inspect the current workflow before assuming older timeout values still apply.

## Experiment index / top page

GitHub Pages:

https://2rwa.github.io/tmp-blender-rigid-cloth/

The top page is now a fixed JavaScript viewer backed by generated experiment data rather than hand/generated HTML cards for every result.

Data model:

- `docs/data/experiments.sqlite` — normalized persistent experiment index
- `docs/data/experiments.json` — denormalized Pages read model
- `data/experiments.sqlite` / `data/experiments.json` — root mirrors for analysis

Viewer source:

- `web/index.html`
- `web/app.js`
- `web/style.css`

The page supports search, category/system/tag filters, sorting, snapshot-first cards, click-to-load videos, summary metrics, and experiment/run/source links.

To add experiments to the top page, publish normal result data into `results/`; do not add cards manually.

Detailed architecture:

- `docs/notes/pages-database-architecture-2026-09-29.md`

## Continuation prompt

The shared Blender continuation instructions are maintained in the workspace:

- repo: `2rwa/chatgpt-workspace`
- path: `prompts/tmp-blender-continuation-prompt.md`

When working in this repository, apply that workflow to `2rwa/tmp-blender-rigid-cloth` and treat this repo's latest `main`, Actions runs, experiments, results, and index database as the source of truth.

## License

Licensing files are inherited from `tmp-blender`; see `LICENSE` and `LICENSES/`.
