# Cloth Drop on Jelly with Delayed Ball EEVEE

A three-system Blender physics experiment for tmp-blender-rigid-cloth.

Sequence:
1. A free 35 x 29 Cloth sheet falls onto the Jelly.
2. At frame 49 (exactly 2.0 s after frame 1 at 24 fps), one Rigid Body ball is released.
3. The ball deforms the Jelly and the Cloth reacts to the baked Jelly and ball motion.

## Coupling strategy

This baseline uses two stable one-way passes rather than a cyclic fully coupled solve:
- Pass 1: delayed Rigid Body ball -> live Soft Body Jelly.
- Pass 2: baked Jelly deformation + baked ball motion -> Cloth.
- The ball does not physically read the Cloth in this baseline.

Both deforming meshes are persisted as 192 per-frame shape keys. The ball is persisted as ordinary transform keyframes, so parallel render jobs do not depend on live physics.

## Profile

- 480 x 360, 24 fps, 192 frames / 8 seconds
- free Cloth sheet with self collision
- rounded translucent Soft Body Jelly cube
- one ball released at frame 49 / 2.0 s
- hidden passive rigid proxy inside Jelly
- EEVEE rendering

## Validation

The validator requires complete Cloth/Jelly shape-key bakes, visible Cloth motion, bounded non-zero Jelly deformation, the exact 2.0-second ball release, rigid proxy metadata, final ball position, and a tunneling diagnostic.

Physics failures such as penetration, jitter, or surprising rebounds are useful experimental evidence and should be kept rather than hidden.
