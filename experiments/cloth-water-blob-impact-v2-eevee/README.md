# Cloth Water-like Blob Impact V2 EEVEE

V2 is a direct response to the visible limitation of V1.

## V1 observation

V1 was numerically successful and passed validation, but visual inspection showed a clear staged-coupling artifact:

- the Soft Body blob deformed and then behaved as if it were returning toward its own goal/original state;
- the Cloth trajectory had already been baked in the earlier pass;
- because the Cloth could no longer react to the final blob motion, it appeared to float above the blob.

The V1 report supports that observation: at the blob deformation peak, the center gap between the already-baked Cloth and final blob surface was about **1.265 units**.

This is retained as useful evidence rather than overwritten.

## V2 architecture: three passes

V2 keeps the dependency graph acyclic:

1. **Guide Cloth -> hidden initial-blob proxy**
   - establishes a plausible Cloth fall/drape trajectory.
2. **Baked Guide Cloth -> live Soft Body blob**
   - deforms the water-like blob without a live Cloth/Soft Body cycle.
3. **Fresh visible Cloth -> baked animated blob**
   - solves Cloth again against the final blob motion.

The third pass is effectively one reconciliation iteration. It does not create true bidirectional coupling, but it should remove the most obvious temporal mismatch that made V1's Cloth float.

## New behavioral metric

V2 compares:

- guide Cloth center gap at blob peak;
- final Cloth center gap at blob peak;
- gap improvement from the third pass.

The validator rejects the run if the final center gap at the blob deformation peak remains above **0.35 units**.

This deliberately upgrades the success definition from:

> "the two solvers interacted at some point"

to:

> "the visible Cloth remains spatially consistent with the final baked blob when the blob is strongly deformed."

## Still not a true fluid

The blue object remains a Soft Body approximation, not Mantaflow. The purpose of V2 is to learn how far staged deformable-object coupling can be pushed before moving to a real fluid solver.
