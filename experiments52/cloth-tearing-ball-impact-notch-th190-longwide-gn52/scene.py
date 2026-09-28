from pathlib import Path
import sys
sys.path.insert(0,str(Path.cwd()))
from experiments52._shared.impact_tearing import run
CONFIG={
  "experiment": "cloth-tearing-ball-impact-notch-th190-longwide-gn52",
  "pattern": "notch",
  "impact_z": 2.02,
  "tear_half_width": 0.22,
  "threshold": 1.9,
  "stretchiness": 0.052,
  "ball_radius": 0.34,
  "ball_start": [0, -2.3, 2.02],
  "ball_impact": [0, -0.32, 2.02],
  "ball_end": [0, 1.1, 2.02],
  "impact_frame": 26,
  "end_frame": 42,
  "render_end_frame": 144,
  "substeps": 14,
  "constraint_steps": 32,
  "camera_location": [0, -10.5, 2.35],
  "camera_target": [0, 0, 2.15],
  "camera_lens": 54,
  "ball_color": [0.82, 0.25, 0.05, 1],
}
if __name__=="__main__": run(CONFIG)
