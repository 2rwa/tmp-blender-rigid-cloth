# tmp-blender-rigid-cloth

Public Blender sandbox focused on rigid-body, cloth, collision, and combined physics experiments.

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

## Repository layout

- `.github/workflows/blender-experiment.yml` — Actions simulation/render/publish pipeline
- `tools/experiment.py` — discovery, planning, validation, publishing helpers
- `tools/build_pages.py` — GitHub Pages gallery builder
- `experiments/` — experiment source
- `results/` — generated persistent outputs
- `docs/` — GitHub Pages output
- `docs/notes/START-HERE.md` — local continuation notes

## Development workflow

1. Inspect and reuse the existing experiment and tools first.
2. Run cheap Python/static checks before Blender simulation or rendering.
3. Use GitHub Actions for tests likely to exceed 30 seconds.
4. Preserve failures that are useful physics observations instead of hiding them.
5. Validate the actual movie/result, not only process exit status.

The dedicated movie prepare job allows up to **60 minutes** so heavier physics simulations can be tried without immediately redesigning around short runtime limits.

## Continuation prompt

The shared Blender continuation instructions are maintained in the workspace:

- repo: `2rwa/chatgpt-workspace`
- path: `prompts/tmp-blender-continuation-prompt.md`

When working in this repository, apply that workflow to `2rwa/tmp-blender-rigid-cloth` and treat this repo's latest `main`, Actions runs, experiments, and results as the source of truth.

## GitHub Pages

https://2rwa.github.io/tmp-blender-rigid-cloth/

The Actions workflow publishes validated results into `results/` and rebuilds the Pages content in `docs/`.

## License

Licensing files are inherited from `tmp-blender`; see `LICENSE` and `LICENSES/`.
