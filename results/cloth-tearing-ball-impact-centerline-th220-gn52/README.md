# Ball Impact Tearing — Centerline Threshold 2.20

Overnight centerline threshold sweep at 2.20.

- source commit: `aa660ca7aa9e59dfcbe8a97bfc5ad4fe21ff0664`
- Actions run: `8` (`36463210144`)
- Blender line: **5.2 experimental Cloth Dynamics / Tearing**

![Latest preview](./preview.jpg)

## Validation

```json
{
  "experiment": "cloth-tearing-ball-impact-centerline-th220-gn52",
  "pattern": "centerline",
  "blender_version": "5.2.2 LTS",
  "impact_frame": 28,
  "tear_observed": false,
  "first_tear_frame": null,
  "tear_after_planned_contact": false,
  "base_vertices": 1575,
  "max_vertices": 1575,
  "max_components": 1,
  "tear_edge_count": 310,
  "custom_mode_applied": true,
  "preview_frame": 36,
  "preview_sha256": "6c2a28be83c53bb2b28a40b233fe0396638d5470852994095bc8c86974fee2ad",
  "video_size_bytes": 78125,
  "blend_size_bytes": 320797
}
```
