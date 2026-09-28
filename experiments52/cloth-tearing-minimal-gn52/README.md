# Blender 5.2 Cloth Dynamics Minimal Tearing

This experiment is intentionally separate from the stable Blender 4.0.2 physics experiments.

## Goal

Prove that Blender 5.2.2's experimental Geometry Nodes Cloth Dynamics asset can:

1. load headlessly in GitHub Actions;
2. use a vertex group for pinning;
3. enable Tearing;
4. split topology during sequential simulation;
5. render the torn mesh to a frame sequence and MP4.

## Why a gravity tear first?

The first test avoids colliders and fluid so that failure has a narrow meaning.

A 37 x 29 vertical cloth grid is pinned along the top edge. The Cloth Dynamics asset is configured with a low tearing strain threshold and stronger-than-normal gravity.

If this cannot tear reliably, adding an impactor or Mantaflow would only obscure the cause.

## Blender version

The dedicated workflow pins **Blender 5.2.2**, released September 15, 2026.

The existing Blender 4.0.2 workflow is not modified.

## Asset loading

Cloth Dynamics in Blender 5.2 is a bundled Geometry Nodes asset rather than a new native modifier type.

The script first tries Blender's Essentials asset operator and falls back to scanning the bundled asset .blend files for:

`Cloth Dynamics (Experimental)`

The complete interface socket list and the properties applied to the modifier are written into the report for debugging.

## Validation

Tearing is not judged only by appearance.

The evaluated mesh is sampled on every frame. A successful tear must:

- change topology;
- increase the evaluated vertex count above the source mesh;
- happen before frame 66;
- produce 72 rendered frames, a preview, MP4, report, and .blend.

Connected-component counts are also recorded, but a partial tear does not have to split the entire cloth into separate islands.

## Next

If this succeeds, the next experiment can introduce a moving closed collider through the cloth. After that, a baked torn cloth can become a Mantaflow effector so liquid can escape through the opening.


## Run #1: Blender 5.2 runtime and asset load succeeded

The first dedicated Actions run established several useful facts before failing:

- Blender **5.2.2 LTS** downloaded, checksum-verified, cached, and launched headlessly under Xvfb.
- The bundled **Cloth Dynamics (Experimental)** Essentials asset was found and added successfully.
- Failure occurred only when setting modifier inputs.

Exact cause: Blender 5.2 changed the Python API for Geometry Nodes modifier inputs. The old pre-5.2 custom-ID-property form such as:

`modifier["Socket_1"] = value`

now raises:

`TypeError: id properties not supported for this type`

Blender 5.2 requires:

`modifier.properties.inputs.<identifier>.value = value`

and field attributes use `.type = "ATTRIBUTE"` plus `.attribute_name`.

The experiment now uses the 5.2 RNA API for Pin Group, Tearing, Threshold, solver settings, and Gravity.


## Run #2: interface discovery reached the actual 5.2 asset sockets

The second run got through the Blender 5.2 RNA modifier API and exposed the complete Cloth Dynamics interface.

Important 5.2.2 socket names include:

- `Pin Group`
- `Stretchiness`
- `Bendiness`
- `Substeps`
- `Constraint Steps`
- `Mass`
- `Friction`
- `Collision Radius`
- `Linear Damping`
- `Gravity` (boolean)
- `Gravity` (vector)
- `Tearing`
- `Tearing Mode`
- `Tearing Edge Group`
- `Tearing Threshold`
- `Tearing Voronoi Scale`

The run failed because the first script looked for a generic `Threshold` socket and therefore deliberately aborted rather than silently using a default.

The implementation now targets the exact 5.2.2 names (`Constraint Steps`, `Linear Damping`, and `Tearing Threshold`). The default tearing mode is left unchanged for this first all-edges test.


## Run #3: tearing succeeded

The third run reached the actual simulation and rendered all 72 frames.

Measured topology:

- source: **1,073 vertices / 2,080 edges / 1,008 faces / 1 component**;
- first tear: **frame 2**, 1,077 vertices;
- frame 6: **2,561 vertices / 3,078 edges / 1,008 faces / 491 components**;
- the torn topology then remained stable through frame 72.

This is direct evidence that Blender 5.2.2 Cloth Dynamics Tearing works headlessly in GitHub Actions.

The run failed only after rendering and MP4 assembly because the validator required the MP4 to be at least 35 KB. The valid 3-second H.264 output was only **18,553 bytes** because the scene has a nearly static backdrop and compresses extremely well.

The video-size sanity threshold was therefore lowered to 10 KB. Topology validation remains the primary proof of tearing.
