# START HERE

## Purpose

`2rwa/tmp-blender-rigid-cloth` is the public specialist repository for Blender rigid-body, cloth, collision, and hybrid physics experiments.

It was bootstrapped from the working infrastructure in `2rwa/tmp-blender`, but only the reusable pipeline and the current Cloth + Rigid Body checkpoint were brought across.

## Source of truth

Always inspect the latest `main` and current GitHub Actions runs before changing an experiment.

Shared continuation prompt:

- `2rwa/chatgpt-workspace`
- `prompts/tmp-blender-continuation-prompt.md`

That prompt documents the original checkpoint and implementation traps. In this repo, substitute `2rwa/tmp-blender-rigid-cloth` as the working source of truth.

## Initial checkpoint

Experiment: `cloth-hammock-rigidbody-drop-eevee`

Known-good implementation rules:

- Cloth and Bullet rigid bodies are sampled in one strictly sequential frame pass.
- Cloth evaluated mesh coordinates are persisted as per-frame shape keys.
- Rigid-body evaluated `matrix_world` transforms are persisted as ordinary location / quaternion / scale keyframes.
- Do not use `bpy.ops.rigidbody.bake_to_keyframes()` in headless Actions.
- Blender 4.0.2 uses `RigidBodyWorld.substeps_per_frame`, not `steps_per_second`.
- Movie validators must return top-level `"video": "<filename>.mp4"` so publishing copies the movie into results and Pages.

## Interesting failure to preserve

The original successful movie showed some spheres tunneling through the cloth/proxy. Treat this as a useful physics observation rather than only a visual defect.

Useful comparison variables include:

- rigid-body `substeps_per_frame`
- solver iterations
- sphere speed / release height / radius
- collision margin
- cloth collision quality and thickness/distance
- proxy shape and thickness
- release staggering
- frame rate

For comparisons, keep the scene setup fixed and change one variable at a time. Record measurable outcomes such as tunneled sphere count, minimum Z, and abnormal post-collision velocity.

## Build / test discipline

Follow `2rwa/chatgpt-workspace/docs/build-test-fix.md`:

- inspect first
- build tests with the feature
- measure rather than infer
- cheap checks first
- fix root causes
- keep regression coverage
- use Actions for long tests
- for generated result writers: pull/rebase → generate → add → commit → push

The workflow's physics prepare job currently has a 60-minute timeout.
