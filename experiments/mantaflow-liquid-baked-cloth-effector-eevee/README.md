# Mantaflow Liquid + Baked Deforming Cloth Effector EEVEE

This experiment advances the successful static Cloth-shaped Mantaflow baseline.

## Goal

Test whether Blender 4.0.2 headless Mantaflow can correctly read a **deforming Cloth surface** when that Cloth motion has first been baked to ordinary shape-key animation.

This is the first bridge between the earlier Cloth work and true liquid.

## Two phases

### Phase 1 — Cloth

A 41 x 35 Cloth grid is pinned around its perimeter and allowed to sag under gravity.

- real Blender Cloth solver
- 1,435 vertices
- self collision enabled
- perimeter pinned
- 96 sequential frames evaluated
- evaluated mesh baked to `Basis + Sim_001..Sim_096` shape keys
- live Cloth modifier removed

### Phase 2 — Mantaflow

The baked animated Cloth receives a Fluid Effector modifier:

- Effector type: Collision
- planar/unclosed surface enabled
- 3 effector subframes

A true Mantaflow Liquid / FLIP block falls onto the deforming Cloth while Mantaflow is baked.

The important dependency direction is now:

**baked deforming Cloth -> liquid**

There is still no liquid pressure/force fed back into the Cloth.

## Why bake first?

A live Cloth solver and live fluid solver would introduce a much harder coupled-system problem. Baking Cloth first gives Mantaflow a deterministic animated obstacle and keeps the dependency graph acyclic.

This follows the lesson from the Soft Body/Cloth experiments: establish stable one-way stages before attempting feedback.

## Validation

The validator requires:

- all 96 Cloth frames baked;
- >= 97 Cloth shape keys including Basis;
- Cloth maximum displacement >= 0.15;
- Cloth center sag >= 0.18;
- Mantaflow cache present and non-trivial;
- meaningful liquid mesh;
- liquid descends into the Cloth region;
- liquid spreads laterally.

## Next step if successful

The next useful experiment is not immediately full two-way fluid-structure interaction.

A safer next test is:

1. liquid -> a second simplified force proxy;
2. proxy drives a second Cloth solve;
3. compare that reconciled Cloth against the original baked Cloth.

That would be the fluid analogue of the staged reconciliation approach that worked for the Soft Body V3 series.
