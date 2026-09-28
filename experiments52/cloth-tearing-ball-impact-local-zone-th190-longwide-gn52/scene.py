from pathlib import Path
import sys
sys.path.insert(0,str(Path.cwd()))
from experiments52._shared.impact_tearing import run
CONFIG={
  "experiment": "cloth-tearing-ball-impact-local-zone-th190-longwide-gn52",
  "pattern": "local-zone",
  "impact_z": 2.08,
  "tear_radius": 0.68,
  "threshold": 1.9,
  "stretchiness": 0.05,
  "ball_radius": 0.3,
  "ball_start": [0, -2.45, 2.08],
  "ball_impact": [0, -0.28, 2.08],
  "ball_end": [0, 1.2, 2.08],
  "impact_frame": 24,
  "end_frame": 38,
  "render_end_frame": 144,
  "substeps": 16,
  "constraint_steps": 30,
  "camera_location": [0, -10.5, 2.35],
  "camera_target": [0, 0, 2.15],
  "camera_lens": 54,
  "ball_color": [0.08, 0.72, 0.3, 1],
}
if __name__=="__main__": run(CONFIG)
