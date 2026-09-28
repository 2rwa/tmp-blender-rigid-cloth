# Ball Impact Tearing — Centerline Threshold 1.35

Threshold calibration run at 1.35, intended to bracket the transition from immediate gravity-driven tearing to impact-triggered tearing.

- source commit: `fdeb60aae5c9d8690f0e91ca944492840a347284`
- Actions run: `6` (`36414569236`)
- Blender line: **5.2 experimental Cloth Dynamics / Tearing**

![Latest preview](./preview.jpg)

## Validation

```json
{
  "experiment": "cloth-tearing-ball-impact-centerline-th135-gn52",
  "pattern": "centerline",
  "blender_version": "5.2.2 LTS",
  "impact_frame": 28,
  "tear_observed": true,
  "first_tear_frame": 2,
  "tear_after_planned_contact": false,
  "base_vertices": 1575,
  "max_vertices": 1860,
  "max_components": 86,
  "tear_edge_count": 310,
  "custom_mode_applied": true,
  "preview_frame": 31,
  "preview_sha256": "893697be11b92af446327dc6b2291bc2f6c1884774b7646f6a6d1b1d708e6e4d",
  "video_size_bytes": 73983,
  "blend_size_bytes": 320760
}
```
