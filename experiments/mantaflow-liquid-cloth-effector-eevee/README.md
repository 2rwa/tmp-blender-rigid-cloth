# Mantaflow Liquid + Cloth Effector EEVEE

This is the first true-fluid experiment after the Soft Body water-like blob V1-V3 series.

## Why this experiment exists

The staged Soft Body approach produced useful results, including a visually coherent V3, but it is still not water.

This experiment switches to Blender's built-in Mantaflow liquid solver.

## Scope

The first test deliberately isolates one question:

> Can Blender 4.0.2, running headless in GitHub Actions, bake and render a real Mantaflow liquid that collides with a Cloth-like planar effector?

The Cloth object is static here. It is a dense red grid shaped like a shallow hammock/basin and configured as:

- Fluid modifier
- Type: Effector
- Effector type: Collision
- planar/unclosed mesh mode enabled

The liquid starts as a geometry volume above it and falls under gravity.

## Coupling

This test is explicitly **one-way**:

- Cloth geometry affects liquid: yes
- liquid forces affect Cloth: no
- true liquid: yes

That distinction is kept in the report so this baseline is not confused with full two-way fluid-structure interaction.

## Runtime strategy

Unlike the existing frame-sequence experiments, Mantaflow depends on an external cache directory.

For this first proof, bake and render therefore happen in the **same standard Actions job**:

1. create scene;
2. save the blend;
3. bake Mantaflow with `bpy.ops.fluid.bake_all()`;
4. sample liquid mesh geometry at several frames;
5. render the 4-second MP4;
6. render a preview;
7. validate cache files, fluid mesh geometry, descent and lateral spread.

This avoids changing the shared parallel-render pipeline before confirming that Mantaflow itself works reliably in the headless runner.

## Initial settings

- Blender 4.0.2
- EEVEE
- Mantaflow Liquid / FLIP
- domain resolution: 48
- 96 frames / 24 fps / 4 seconds
- 480 x 360
- liquid mesh enabled
- initial liquid geometry block above Cloth
- static Cloth-like planar effector

## Next step if successful

Bake a real Cloth simulation first, replay it as an animated Fluid Effector, and test **baked deforming Cloth -> Mantaflow liquid**.

Only after that is stable is it worth investigating feedback in the other direction or an external solver such as FLIP Fluids.
