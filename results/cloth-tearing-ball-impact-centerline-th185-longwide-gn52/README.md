# Ball Impact Tearing — Centerline 1.85 Long Wide

Long-view 144-frame centerline calibration at threshold 1.85.

- source commit: `a29c215dff6b583e39bb58439cacff79a00d6bdb`
- Actions run: `9` (`36472219772`)
- Blender line: **5.2 experimental Cloth Dynamics / Tearing**

![Latest preview](./preview.jpg)

## Validation

```json
{
  "experiment": "cloth-tearing-ball-impact-centerline-th185-longwide-gn52",
  "pattern": "centerline",
  "blender_version": "5.2.2 LTS",
  "impact_frame": 28,
  "frame_end": 144,
  "duration_seconds": 6.0,
  "tear_observed": true,
  "first_tear_frame": 2,
  "tear_after_planned_contact": false,
  "base_vertices": 1575,
  "max_vertices": 1628,
  "max_components": 12,
  "tear_edge_count": 310,
  "custom_mode_applied": true,
  "preview_frame": 31,
  "preview_sha256": "b2c07de0e0ebc87564ef8fb5eb553aecb00ca97b867336a639612bc81a647493",
  "video_size_bytes": 67062,
  "blend_size_bytes": 320762
}
```
