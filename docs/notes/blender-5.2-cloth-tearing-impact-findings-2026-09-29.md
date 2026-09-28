# Blender 5.2 Cloth Tearing / Impact findings — 2026-09-29

Date: 2026-09-29 (JST)

This note records the current state of the Blender 5.2.2 LTS experimental Cloth Dynamics / Tearing impact line after the 5-case and 10-case parameter sweeps.

It intentionally records reusable technical observations rather than conversation history.

## Current implementation

Primary workflow:

- `.github/workflows/blender52-impact-batch.yml`
- Blender **5.2.2 LTS**
- Geometry Nodes asset: **Cloth Dynamics (Experimental)**
- collider asset: **Collider**
- headless Ubuntu GitHub Actions
- EEVEE
- runtime cache + per-experiment render checkpoint
- artifact upload
- persistent publication to `results/`
- gallery rebuild and GitHub Pages deployment

Current heavy render timeout:

- **180 minutes**

Current batch can run:

- **10 experiments in parallel**
- publish serially afterward
- Pages deployment after all published results succeed

The long-view experiments use:

- 144 frames
- 24 fps
- 6 seconds
- 480 x 360
- a more distant camera than the original 72-frame tests

Run #9 completed all ten 144-frame experiments and the Pages deployment in about **76 minutes**, comfortably inside the 180-minute upper bound.

## Important implementation changes discovered during the work

### Blender 5.2 Geometry Nodes input API

Runtime inputs are written through:

`modifier.properties.inputs.<identifier>.value`

Field inputs such as vertex groups use:

`type = "ATTRIBUTE"`

and an attribute name.

The exact 5.2 Cloth Dynamics socket names matter. Relevant sockets include:

- Stretchiness
- Bendiness
- Substeps
- Constraint Steps
- Mass
- Friction
- Collision Radius
- Linear Damping
- Gravity
- Tearing
- Tearing Mode
- Tearing Edge Group
- Tearing Threshold
- Tearing Voronoi Scale
- Effectors Collection

### Validation should prefer semantic evidence over file size

Observed false failures:

- valid short MP4 below a large byte-size floor
- valid no-contact MP4 of only 9,931 bytes because almost nothing moved
- valid small .blend below an arbitrary large size threshold

For this project:

- topology measurements are primary;
- frame/sample count is primary;
- media file size is only a low corruption sanity check.

### Result publishing and checkpoint recovery

The workflow now supports recovery independent of the chat session:

- render checkpoints
- Actions artifacts
- persistent `results/`
- Pages publication
- reusable Blender runtime cache

This is why long physics jobs now use a generous timeout instead of being cut off early.

## Impact experiment baseline

The impact test builds a cloth grid of:

- 45 x 35 vertices
- 1,575 source vertices
- 3,070 source edges
- 1,496 faces in the normal rectangular cases

The ball is a prescribed animated collider. Coupling is intentionally one-way:

`prescribed collider ball -> Cloth Dynamics`

The evaluated cloth is sampled every frame. Recorded values include:

- vertex count
- edge count
- face count
- connected-component count
- world-space bounds
- ball location

A topology change is currently detected if any of vertices / edges / faces differs from the source topology.

This means a reported `first_tear_frame` can represent a small topology split even if connected components remain 1.

## First 5-case impact sweep

Initial thresholds were roughly 1.095–1.13.

Observed completed cases:

| pattern | threshold | planned impact | first topology change | max components |
| --- | ---: | ---: | ---: | ---: |
| centerline | 1.11 | 28 | 2 | 122 |
| local-zone | 1.095 | 24 | 2 | 163 |
| notch | 1.13 | 26 | 2 | 77 |
| hammock | 1.12 | 30 | 2 | 333 |
| swing | 1.105 | 29 | 2 | 115 |

At this point it looked as if the tearing threshold was simply too low.

## Second threshold calibration sweep

Higher thresholds reduced the amount of destruction strongly, but did not initially remove the frame-2 topology event in the vertical cases.

| pattern | threshold | first topology change | max components |
| --- | ---: | ---: | ---: |
| centerline | 1.20 | 2 | 102 |
| centerline | 1.35 | 2 | 86 |
| centerline | 1.55 | 2 | 52 |
| notch | 1.45 | 2 | 43 |
| hammock fast ball | 1.60 | 3 | 5 |

Useful observation:

Increasing threshold clearly reduces fracture severity. The parameter is active and meaningful.

However, the timing behavior could not be explained by threshold alone.

## Overnight threshold sweep

A wider sweep established an apparent centerline transition:

| threshold | first topology change | max components |
| ---: | ---: | ---: |
| 1.80 | 2 | 15 |
| 2.20 | none | 1 |
| 2.80 | none | 1 |
| 3.60 | none | 1 |
| 5.00 | none | 1 |

Other threshold-2.20 cases:

| pattern | first topology change | max components |
| --- | ---: | ---: |
| notch | none | 1 |
| local-zone | none | 1 |
| hammock fast ball | none | 1 |
| swing fast | 2 | 22 |
| centerline no-contact | none | 1 |

This narrowed the interesting centerline threshold region to roughly **1.8–2.2**, but the next long-run batch revealed a more important issue.

## 144-frame long-view sweep

Run #9:

- workflow run id: `36472219772`
- source commit: `a29c215dff6b583e39bb58439cacff79a00d6bdb`
- result: **success**
- all ten renders: success
- all ten publish jobs: success
- Pages build/deploy: success
- wall-clock duration: about **76 minutes**

Centerline long-view sweep:

| threshold | first topology change | max vertices | max components |
| ---: | ---: | ---: | ---: |
| 1.85 | 2 | 1,628 | 12 |
| 1.90 | 2 | 1,614 | 10 |
| 1.95 | 2 | 1,597 | 4 |
| 2.00 | 2 | 1,581 | 1 |
| 2.05 | 2 | 1,576 | 1 |

Control:

| experiment | threshold | first topology change | max vertices | max components |
| --- | ---: | ---: | ---: | ---: |
| centerline no-contact | 1.95 | **none** | 1,575 | 1 |

Other long-view cases:

| pattern | threshold | first topology change | max components |
| --- | ---: | ---: | ---: |
| notch | 1.90 | 2 | 3 |
| local-zone | 1.90 | 2 | 11 |
| hammock | 1.90 | none | 1 |
| swing | 2.60 | 2 | 18 |

## Strongest current observation: collider-related early instability

The no-contact control changes the interpretation of the earlier runs.

At threshold 1.95:

### Normal centerline ball

Frame 1:

- ball y: about -2.35
- cloth y bounds: about -0.01 to +0.01
- topology: 1,575 vertices, 1 component

Frame 2:

- ball y: about -2.347
- cloth min y: about **-2.73**
- topology: 1,595 vertices, 4 components

The ball has not reached the visually expected cloth contact plane, yet the cloth undergoes a very large displacement toward the negative-y side immediately.

### No-contact control

The same cloth and threshold are used, but the ball path is shifted to x=5.

Frame 2:

- cloth y bounds remain about -0.01 to +0.01
- topology remains 1,575 vertices
- 1 component
- no tear/topology change through all 144 frames

Therefore:

> The current frame-2 event is not adequately explained as gravity-only self tearing.

The presence and spatial placement of the collider/effectors setup materially changes the simulation before the planned impact frame.

This does **not yet prove** a Blender bug. Possible causes include:

- collider asset parameter semantics;
- effectors collection behavior;
- collision margin/radius interpretation;
- simulation initialization;
- numerical instability from cloth properties;
- solver/substep/constraint interaction;
- prescribed collider motion interacting with the solver in a non-obvious way;
- an error in how the current setup configures the bundled experimental Geometry Nodes assets.

The next experiments should distinguish these possibilities instead of only sweeping Tearing Threshold.

## Cloth material / rigidity parameters that must now be explored

Threshold is only one axis. The cloth mechanics themselves are likely important.

Current common vertical-cloth defaults are approximately:

- Stretchiness: **0.05**
- Bendiness: **0.18** (shared default unless overridden)
- cloth Mass: **0.65** (shared default)
- Linear Damping: **0.035**
- Gravity: **(0, 0, -9.81)**
- Substeps: commonly **14–16**
- Constraint Steps: commonly **30–34**

Important clarification:

- the current `mass` config is the **cloth mass input**, not ball rigid-body mass;
- the impact ball is a prescribed animated collider, not a Bullet rigid body.

The next parameter work should explicitly measure:

### Stretch response

Sweep Stretchiness while holding collision and threshold fixed.

Suggested first coarse values:

- 0.02
- 0.05 baseline
- 0.10
- 0.20

Do not assume the intuitive direction of the socket without measurement; record actual deformation/bounds.

### Bending response

Sweep Bendiness around the current 0.18 default.

Suggested coarse values:

- 0.05
- 0.18 baseline
- 0.35
- 0.60

Measure:

- early y displacement
- topology change frame
- maximum displacement
- final deformation
- component count

### Cloth mass

Suggested values:

- 0.35
- 0.65 baseline
- 1.0
- 1.5

Because the collider is prescribed, this tests cloth inertial response rather than a two-way mass ratio.

### Damping

Current Linear Damping is about 0.035.

Suggested values:

- 0.01
- 0.035 baseline
- 0.08
- 0.15

This may help distinguish a genuine collision response from an unstable launch/oscillation.

### Solver quality

Current typical values:

- Substeps: 14–16
- Constraint Steps: 30–34

Suggested diagnostics:

- Substeps: 8 / 14 / 24
- Constraint Steps: 16 / 30 / 60

A result that changes dramatically with solver quality is important evidence of numerical sensitivity.

## Collider parameters that should be isolated

Current collider defaults in the shared script include approximately:

- Deforming: false
- Boundary: false
- Margin: 0.025
- Friction: 0.20
- Softness: 0.0

Recommended controlled tests:

1. ball object present, but no Collider modifier;
2. Collider modifier present, but not in the Effectors Collection;
3. Effectors Collection active, collider far away;
4. collider at the usual x/z but much farther in y;
5. static collider with no animation;
6. Margin = 0;
7. several small positive Margin values;
8. Softness sweep;
9. Friction = 0 versus current value;
10. Boundary mode comparison if its semantics are appropriate for this asset.

The crucial metric is not only tearing. Record cloth bounds at frames 1–8 so the early launch behavior can be detected directly.

## Recommended next experimental structure

Do not immediately launch another large threshold-only sweep.

A more informative next batch is a factorial-style diagnostic split:

### Group A — collider isolation

Keep cloth mechanics fixed near a stable threshold such as 1.95–2.20.

Vary only collider/effectors setup.

### Group B — cloth rigidity

Use a single collider setup and vary:

- Stretchiness
- Bendiness
- Mass
- Linear Damping

### Group C — solver sensitivity

Use the same physical scene and vary:

- Substeps
- Constraint Steps

For each case record at minimum:

- first topology-change frame
- planned impact frame
- vertices / edges / faces
- connected components
- cloth world bounds for early frames
- cloth world bounds at impact
- ball location
- maximum displacement
- whether the no-contact control remains stable

## Long-run / camera implementation

The shared impact script now accepts:

- `render_end_frame`
- `camera_location`
- `camera_target`
- `camera_lens`

This removed the previous hard-coded 72-frame limitation.

The validator now derives expected sample count from the report's frame range rather than assuming exactly 72 samples.

The long-view vertical tests used approximately:

- camera: `(0, -10.5, 2.35)`
- target: `(0, 0, 2.15)`
- lens: 54 mm

The hammock uses a farther diagonal elevated view.

## Current operational state

As of this note:

- 180-minute heavy timeout is working;
- 10-way parallel render matrix is working;
- 144-frame / 6-second experiments complete within the timeout;
- result publication is working;
- Pages publication is working;
- render checkpoint recovery is working;
- no-contact videos may compress below 10 KB and therefore receive a lower validation floor in the workflow.

## Current interpretation

The best-supported conclusions are:

1. Blender 5.2 experimental Cloth Dynamics tearing works headlessly in GitHub Actions.
2. Tearing Threshold strongly controls fracture amount.
3. A threshold region around 1.8–2.2 is interesting for the current centerline setup.
4. Threshold alone does not explain the observed frame-2 behavior.
5. A no-contact control at threshold 1.95 is stable for 144 frames.
6. The normal collider placement at the same threshold causes a huge cloth displacement by frame 2, long before the planned visual impact.
7. Therefore collider/effectors initialization and cloth mechanical parameters must be characterized before interpreting later runs as physically meaningful impact tearing.
8. Stretchiness, Bendiness, cloth Mass, damping, Substeps, and Constraint Steps are now first-class experimental variables, not secondary tuning knobs.

## Next restart point

Start from:

- this note;
- `experiments52/_shared/impact_tearing.py`;
- `experiments52/_shared/validate_impact.py`;
- current `.github/workflows/blender52-impact-batch.yml`;
- run #9 results in `results/cloth-tearing-*-longwide-gn52/`.

First priority:

> isolate the frame-2 collider/effectors response and test whether cloth rigidity / solver quality changes it.

Only after that should the project claim a clean impact-triggered tearing regime.
