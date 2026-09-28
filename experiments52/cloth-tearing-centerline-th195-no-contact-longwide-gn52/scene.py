from pathlib import Path
import sys
sys.path.insert(0,str(Path.cwd()))
from experiments52._shared.impact_tearing import run
CONFIG={
  "experiment": "cloth-tearing-centerline-th195-no-contact-longwide-gn52",
  "pattern": "centerline",
  "impact_z": 2.12,
  "tear_half_width": 0.2,
  "threshold": 1.95,
  "stretchiness": 0.05,
  "ball_radius": 0.36,
  "ball_start": [5, -2.35, 2.12],
  "ball_impact": [5, -0.34, 2.12],
  "ball_end": [5, 1.15, 2.12],
  "impact_frame": 28,
  "end_frame": 43,
  "render_end_frame": 144,
  "substeps": 14,
  "constraint_steps": 30,
  "camera_location": [0, -10.5, 2.35],
  "camera_target": [0, 0, 2.15],
  "camera_lens": 54,
  "ball_color": [0.2, 0.2, 0.2, 1],
}
if __name__=="__main__": run(CONFIG)
