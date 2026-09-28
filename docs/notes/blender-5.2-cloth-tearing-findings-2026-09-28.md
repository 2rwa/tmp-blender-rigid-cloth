# Blender 5.2 Cloth Dynamics / Tearing findings

Date: 2026-09-28 (JST)

This note records technical findings from introducing Blender 5.2.2 LTS Geometry Nodes Cloth Dynamics / Tearing into the existing GitHub Actions physics test environment.

It intentionally excludes conversation history and keeps only reusable implementation knowledge.

## Context

Existing physics experiments in this repository use Blender 4.0.2.

Blender 5.2 introduces a separate experimental Cloth Dynamics system implemented as a bundled Geometry Nodes asset. To avoid destabilizing the proven 4.0.2 workflow, the tearing test uses a separate workflow and experiment root:

- workflow: `.github/workflows/blender52-tearing.yml`
- experiment root: `experiments52/`
- first experiment: `experiments52/cloth-tearing-minimal-gn52/`

The workflow pins **Blender 5.2.2 LTS**.

## Actions runtime findings

The first dedicated workflow run confirmed that Blender 5.2.2 can be used headlessly on the same Ubuntu Actions runner pattern already used for Blender 4.0.2.

Confirmed working:

- official `blender-5.2.2-linux-x64.tar.xz` download;
- checksum verification using the official SHA256 manifest;
- Xvfb headless startup;
- software OpenGL path;
- runtime caching with `actions/cache`;
- bundled Essentials asset access.

Observed successful headless version string:

`BLENDER52_XVFB_OK 5.2.2 LTS`

The runtime is cached separately from the 4.0.2 runtime:

`.cache/blender52-runtime`

## Cloth Dynamics is a Geometry Nodes asset

The 5.2 Cloth Dynamics implementation is not a traditional Cloth modifier replacement with a dedicated modifier type.

It is exposed as a bundled Geometry Nodes asset:

`Cloth Dynamics (Experimental)`

The experiment first tries the Essentials asset operator and includes a fallback that scans bundled asset `.blend` files and loads the matching node group directly.

This is useful for headless automation because UI asset-browser interaction is unnecessary.

## Important Blender 5.2 Python API change

The first run failed after successfully loading the Cloth Dynamics asset.

Old Geometry Nodes modifier input access such as:

```python
modifier["Socket_2"] = value
```

no longer works in Blender 5.2 for these inputs and raises:

`TypeError: id properties not supported for this type`

Blender 5.2 uses RNA runtime input properties under:

```python
modifier.properties.inputs.<identifier>
```

Scalar/vector inputs are written through `.value`.

Field inputs such as a vertex-group driven Pin Group use:

```python
prop.type = "ATTRIBUTE"
prop.attribute_name = "PinnedTop"
```

This is an important migration issue for any Python automation that configures Geometry Nodes modifiers in Blender 5.2.

## Actual Cloth Dynamics socket names in Blender 5.2.2

The second run intentionally dumped the real interface after the RNA migration was fixed.

Observed input sockets:

- `Geometry`
- `Pin Group`
- `Invert Pin Group`
- `Stretchiness`
- `Bendiness`
- `Substeps`
- `Constraint Steps`
- `Simulation to World`
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
- `Effectors Collection`
- `Cloth Tags`
- `Extra Sim Attributes`
- `Effectors`

Do not assume manual section headings map directly to socket names.

Examples of exact names that mattered:

- use `Constraint Steps`, not `Constraint Iterations`;
- use `Linear Damping`, not a generic `Linear`;
- use `Tearing Threshold`, not a generic `Threshold`.

Failing loudly when an expected socket is missing proved useful: it exposed the actual 5.2.2 interface instead of silently running with defaults.

## Minimal tearing experiment design

The first tearing test intentionally avoids colliders and fluids.

Scene:

- vertical cloth grid: 37 x 29;
- top row pinned by vertex group;
- strong gravity;
- low tearing threshold;
- 72 frames at 24 fps;
- EEVEE;
- 480 x 360.

The goal is to isolate one question:

> Can the Blender 5.2 Cloth Dynamics asset tear topology reliably in GitHub Actions?

Only after this baseline is stable should impact objects or Mantaflow be introduced.

## Validation strategy

Tearing should not be judged only visually.

The experiment samples the evaluated mesh every frame and records:

- vertex count;
- edge count;
- face count;
- connected-component count;
- bounds.

A successful tear is expected to produce a topology change, especially an increase in evaluated vertex count as edges split.

The validator requires:

- Blender 5.2.2;
- Tearing enabled;
- detected topology change;
- first tear before frame 66;
- max evaluated vertex count greater than the source vertex count;
- 72 sampled frames;
- preview, MP4, report, and .blend outputs.

Connected-component count is recorded as supporting evidence but is not required to increase, because a partial tear can split edges without completely separating the cloth into multiple islands.

## Run history

### Run #1

Workflow: Blender 5.2 tearing experiment #1

Result:

- Blender 5.2.2 runtime build: success;
- headless launch: success;
- Cloth Dynamics asset load: success;
- scene setup: failed while writing modifier inputs.

Cause:

`TypeError: id properties not supported for this type`

Lesson:

Geometry Nodes modifier input automation must use the Blender 5.2 RNA API.

### Run #2

Workflow: Blender 5.2 tearing experiment #2

Result:

- cached runtime restore: success;
- headless launch: success;
- Cloth Dynamics asset load: success;
- RNA input access: success;
- scene setup aborted before simulation.

Cause:

the script searched for a generic `Threshold` socket, but the asset exposes `Tearing Threshold`.

The full real socket interface was captured and used to correct the script.

### Run #3

Workflow run id: `36357349539`

Final result:

- runtime restore: success;
- headless verification: success;
- asset loading: success;
- Blender 5.2 RNA input configuration: success;
- real socket-name configuration: success;
- 72-frame tearing simulation: success;
- 72-frame render: success;
- MP4 assembly: success;
- final validator: failed only because a valid 18,553-byte MP4 was below an overly conservative 35 KB size threshold.

Measured topology:

- source: 1,073 vertices / 2,080 edges / 1,008 faces / 1 component;
- first tear: frame 2, 1,077 vertices;
- frame 6: 2,561 vertices / 3,078 edges / 1,008 faces / 491 components;
- torn topology remained stable through frame 72.

This confirms that Blender 5.2.2 Cloth Dynamics Tearing works headlessly in GitHub Actions.

## Current source commits

Initial Blender 5.2 experiment:

`2f80e6a60467d3d18da4b0a2f53471cf4d1b8672`

Blender 5.2 RNA modifier API fix:

`cb5961b7d2d61da15b776c901c4d6a04a9a1cc00`

Exact 5.2.2 socket-name fix:

`5eff8de30cff5e514554f785040b3f11337252ff`

## Next decision point

After run #3 completes:

1. confirm whether topology actually changed;
2. inspect the first tear frame and growth in vertex count;
3. inspect visual quality of the tear;
4. if stable, add an impact collider;
5. after that, bake torn Cloth and use it as a Mantaflow effector so liquid can pass through the opening.

The existing Blender 4.0.2 physics workflow should remain untouched while the 5.2 experimental line is still being characterized.


## Run #3 validator lesson

A tiny MP4 is not a reliable failure signal for short, visually simple simulation clips.

The 72-frame / 3-second tearing video was only 18,553 bytes because H.264 compressed the mostly static background extremely well. The physical/topological evidence was strong and the full frame sequence had rendered successfully.

For this class of test:

- topology change is the primary semantic proof;
- frame count / preview existence are stronger media sanity signals than a large byte-size threshold;
- use only a low floor (10 KB here) to catch empty/corrupt MP4 outputs.
