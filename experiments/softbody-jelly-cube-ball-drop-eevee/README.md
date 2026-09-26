# Soft Body Jelly Cube Ball Drop EEVEE

A Blender hybrid-physics experiment for `tmp-blender-rigid-cloth`.

Three active rigid-body spheres start at different heights and fall under normal scene gravity onto a rounded Soft Body jelly cube. The experiment deliberately combines two Blender solvers through a practical one-way coupling:

- Bullet Rigid Body drives the falling balls;
- each ball also has a Collision modifier, so the Soft Body solver sees its evaluated motion;
- an invisible passive rigid proxy sits inside the jelly so the rigid balls have something physical to bounce from;
- the proxy is smaller than the visible jelly, allowing visible squash before the rigid collision response.

This is not intended to be a mathematically exact two-way soft/rigid coupling. It is a reproducible visual/physics experiment that lets us observe deformation, rebound, oscillation, and tunneling-like failures.

## Profile

- 480 x 360
- 24 fps
- 192 frames / 8 seconds
- 3 gravity-driven rigid-body spheres
- staggered impact timing via different initial heights
- rounded translucent Soft Body jelly cube
- hidden passive rigid-body proxy
- EEVEE rendering

## Headless bake strategy

Simulation is advanced strictly sequentially from frame 1 through 192.

For every frame:

1. sample the evaluated Soft Body mesh;
2. sample each rigid body's evaluated `matrix_world`;
3. reject runaway Soft Body deformation early;
4. keep simple per-ball collision diagnostics.

After the simulation pass:

- Jelly deformation is persisted as `Basis + Sim_001 ... Sim_192` shape keys.
- Live Soft Body is removed from the prepared scene.
- Rigid-body locations, quaternions, and scales are persisted as normal object keyframes.
- The rigid balls are switched to kinematic mode so parallel render jobs no longer depend on a live Bullet simulation.

This follows the successful headless patterns already established in the repository and avoids `bpy.ops.rigidbody.bake_to_keyframes()`.

## Validation

The validator checks the actual rendered outputs and prepared scene, including:

- movie and preview dimensions;
- 8-second duration;
- 192 baked Jelly frames;
- non-zero but bounded Jelly deformation;
- exactly 3 rigid balls;
- rigid proxy presence;
- per-ball final positions and tunneling diagnostics.

`possible_proxy_tunneling` is recorded as an observation rather than automatically treated as a failed experiment. Physics failures are useful results here.

## Useful next comparisons

Keep the same scene and vary one parameter at a time:

- Soft Body Goal strength / spring / damping;
- rigid-body mass;
- sphere radius;
- initial drop height;
- rigid-body `substeps_per_frame`;
- solver iterations;
- proxy size / depth;
- 1 vs 3 vs 5 balls.
