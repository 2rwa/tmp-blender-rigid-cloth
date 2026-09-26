# Cloth Water-like Blob Impact V3 EEVEE

V3 follows the successful V2 reconciliation pass.

## Why V3 exists

V2 solved the major V1 floating artifact numerically:

- guide Cloth gap at blob peak: 1.285187;
- final Cloth gap at blob peak: **0.059224**;
- improvement: **1.225963**;
- maximum positive gap after contact: **0.161919**.

Visual inspection nevertheless produced an interesting new artifact: the water-like blob could look as if it were **eating / swallowing the Cloth**.

That makes sense structurally. In V2 the final Cloth collides directly with the exact baked visible blob surface. Small solver offsets and fast local shape changes can put the rendered surfaces extremely close or slightly interpenetrating.

This is not the same failure as V1: the Cloth is no longer floating far away. The remaining problem is surface separation.

## V3 idea: collision shell

V3 keeps the same acyclic three-pass architecture:

1. guide Cloth -> hidden initial proxy;
2. baked guide Cloth -> live Soft Body blob;
3. fresh visible Cloth -> baked blob motion.

The only major change is pass 3.

A hidden object shares the blob's exact baked Mesh/shape-key animation, but its object scale is slightly expanded:

- X/Y: 1.045
- Z: 1.070
- collision thickness: 0.014

The visible blob is unchanged. The expanded object exists only as a Cloth collision envelope and is removed after the final Cloth is baked.

This is analogous to a collision skin around a rendered character mesh.

## Success condition

V3 now rejects both directions of visual failure:

- **ingestion / excessive penetration:** center gap after contact < -0.12;
- **floating:** center gap after contact > 0.35.

At maximum blob deformation, the visible Cloth/blob gap should remain in the useful band:

**-0.05 to 0.30 units**.

If this works, the approximation is still not a true two-way fluid/cloth solve, but it is a practical visually coherent staged method.

If it does not work, the remaining artifact is likely inherent enough to this staged Soft Body approximation that the next useful step should be Mantaflow/FLIP rather than adding more reconciliation passes.
