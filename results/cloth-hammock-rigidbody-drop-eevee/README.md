# Cloth Hammock Rigid Body Drop EEVEE

Hybrid cloth + rigid-body experiment: 12 staggered rigid-body spheres fall into a four-corner-pinned cloth hammock. A hidden passive rigid proxy provides stable two-system coupling while the visible cloth reacts to the moving spheres. Physics is baked before parallel EEVEE rendering.

- source commit: `872f3e7cda2fe01f2da6a661143f47c1f3302168`
- Actions run: `1` (`36243544214`)
- full artifact: `blender-cloth-hammock-rigidbody-drop-eevee`

## Blend files

- Git: [cloth-hammock-rigidbody-drop-eevee.blend](./cloth-hammock-rigidbody-drop-eevee.blend) (7,609,332 bytes)

![Latest preview](./preview.jpg)

## Validation

```json
{
  "video": "cloth-hammock-rigidbody-drop-eevee.mp4",
  "preview": {
    "path": "output/preview.png",
    "size_bytes": 224301,
    "width": 480,
    "height": 360,
    "luminance_min": 0,
    "luminance_max": 191,
    "luminance_mean": 60.851,
    "luminance_stddev": 65.222,
    "sha256": "20a978c293b9a491f5c4863b940027665f80f4d5ecd70e465568be189d4f317a"
  },
  "movie": {
    "path": "output/cloth-hammock-rigidbody-drop-eevee.mp4",
    "size_bytes": 156795,
    "width": 480,
    "height": 360,
    "duration_seconds": 8.0,
    "avg_frame_rate": "24/1",
    "nb_frames": "192",
    "sha256": "fc902f8a4752f0e2dcaf191dd0df64736a23863532b2f9780e6ef8867e47cf25"
  },
  "report": {
    "engine": "BLENDER_EEVEE",
    "vertex_count": 1575,
    "face_count": 1496,
    "pinned_vertex_count": 36,
    "baked_shape_keys": 192,
    "shape_key_count": 193,
    "simulation_seconds": 15.932,
    "rigid_body_count": 12,
    "rigid_body_bake_seconds": 0.122,
    "rigid_body_proxy": "RigidHammockProxy",
    "effectors": [
      "CrossWind",
      "Turbulence"
    ],
    "blend_size_bytes": 7609332
  }
}
```

## License / ライセンス

Unless otherwise noted, generated assets in this result (including rendered images, video, and generated .blend files) are CC0-1.0. Source code and workflow files used to generate them are MIT-0.

特記のない限り、この成果物内の生成アセット（レンダリング画像、動画、生成された .blend ファイル等）は CC0-1.0、生成に使用したソースコードや workflow は MIT-0 です。

Third-party data, assets, or source material remain subject to their original licenses and terms. These repository licenses apply only to rights we are entitled to grant.

第三者のデータ・アセット・素材・ソースを利用している部分は、利用元のライセンスおよび利用条件に従います。このリポジトリのライセンスは、こちらが許諾できる権利にのみ適用されます。

See ../../LICENSE and ../../LICENSES/ for details.
