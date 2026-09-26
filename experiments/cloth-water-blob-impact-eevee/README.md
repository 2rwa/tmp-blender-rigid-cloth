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
