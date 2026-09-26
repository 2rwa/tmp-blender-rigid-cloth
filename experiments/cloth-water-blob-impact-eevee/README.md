# Cloth Water-like Blob Impact EEVEE

This experiment is the first step from Jelly toward water.

It intentionally does **not** use Mantaflow or a true fluid solver. A flattened translucent Soft Body object acts as a water-like deformable mass while a free Cloth sheet falls onto it.

## Question

Can Blender 4.0.2 evaluate a Soft Body blob and Cloth in the same sequential headless pass when both deforming objects are also exposed as Collision objects?

If it works, this gives a cheap baseline before introducing true fluid simulation. If it fails, the failure is useful evidence about cyclic solver dependencies.

## Scene

- 480 x 360
- 24 fps
- 192 frames / 8 seconds
- EEVEE
- one flattened blue translucent Soft Body blob
- one red Cloth sheet
- Cloth self collision enabled
- no ball and no rigid proxy in this first test
- both Cloth and blob are sampled sequentially and baked to per-frame shape keys before parallel rendering

## Behavioral validation

The validator requires more than a valid MP4:

- the blob must actually deform;
- Cloth/Blob contact must be detected;
- at least 45% of Cloth vertices must remain horizontally over the blob at the blob deformation peak;
- the center gap between Cloth and blob must be small enough to indicate contact;
- both deformers must contain all 192 baked frames.

The report explicitly marks `true_fluid: false` so this approximation is not confused with Mantaflow.

## Run #5: direct live coupling failure

The first implementation made the live Cloth and live Soft Body blob Collision objects for each other. Blender 4.0.2 reported explicit dependency cycles:

- Soft Body depended on Cloth geometry via Softbody Collision;
- Cloth depended on blob geometry via Cloth Collision;
- both modifier stacks therefore closed a dependency loop.

The simulation continued far enough to show progressive instability, then the fail-fast guard stopped it at frame 179 when blob displacement exceeded 8 units.

This is useful evidence: direct mutual live Cloth/Soft Body Collision is not a valid dependency-graph architecture for this headless experiment.

The corrected version uses staged coupling:

1. Cloth falls against a smaller hidden proxy inside the intended blob volume and is baked.
2. The proxy is removed.
3. The baked animated Cloth becomes a deterministic collider.
4. The live Soft Body blob is simulated against that baked Cloth and then baked.

This preserves a measurable Cloth -> blob response while breaking the dependency cycle.

## Next steps

If this direct live coupling is stable:

1. soften the blob further;
2. try two blobs;
3. add a delayed ball;
4. compare a metaball render representation;
5. move to a minimal Mantaflow Cloth splash experiment.

If the direct coupling is unstable or the blob does not react to Cloth, keep the failure and fall back to a staged/baked coupling experiment.


## Run #6: staged coupling rendered, validator exposed a coordinate-space bug

The staged architecture fixed the dependency cycle completely:

- prepare succeeded;
- both Cloth and Soft Body were baked to 192 frames;
- all eight frame-render chunks succeeded;
- MP4 assembly succeeded.

The run failed only at semantic validation with:

`cloth never reached the live blob envelope`

The prepared report showed that this was a measurement bug, not a failed solve. Cloth metrics were effectively in world space because the Cloth object is at the origin, while blob mesh vertices were compared in object-local space even though `WaterBlob` is translated upward by `z = 0.88`.

Observed staged solve before correcting the metric:

- blob maximum displacement: 1.602471 at frame 64;
- blob center-top drop: 1.446784;
- Cloth coverage at the blob peak: 97.97%;
- Cloth simulation: 16.919 s;
- blob simulation: 10.803 s;
- all 192 rendered frames completed.

The corrected version transforms evaluated geometry to world space for contact/height measurements while retaining local coordinates for shape-key baking.

Another useful observation is that Soft Body collision response may push the blob surface away from the already-baked Cloth after initial overlap. Therefore a near-zero center gap is not required as the sole proof of interaction; displacement, center-top drop, coverage, and minimum world-space gap are evaluated together.


## Run #7: world-space metric patch typo

The world-space correction itself worked: the Cloth pass reported a center gap of about `-0.18` after settling, confirming that the baked Cloth penetrates the intended full-size blob envelope as designed.

The run then stopped before the Soft Body pass because the patch referenced `cloth` inside `bake_blob_pass()` without passing that object into the function. This was a plain Python `NameError`, not a Blender physics failure. The function signature and call were corrected in the next run.
