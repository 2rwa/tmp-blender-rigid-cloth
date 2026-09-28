from pathlib import Path
import sys
sys.path.insert(0,str(Path.cwd()))
from experiments52._shared.impact_tearing import run
CONFIG={
  "experiment": "cloth-tearing-ball-drop-hammock-th190-longwide-gn52",
  "pattern": "hammock",
  "tear_radius": 0.95,
  "threshold": 1.9,
  "stretchiness": 0.055,
  "ball_radius": 0.58,
  "ball_start": [0, 0, 4.9],
  "ball_impact": [0, 0, 2.62],
  "ball_end": [0, 0, 0.55],
  "impact_frame": 20,
  "end_frame": 38,
  "render_end_frame": 144,
  "substeps": 16,
  "constraint_steps": 34,
  "mass": 0.72,
  "camera_location": [7.8, -9.2, 5.8],
  "camera_target": [0, 0, 1.95],
  "camera_lens": 52,
  "ball_color": [0.62, 0.12, 0.78, 1],
}
if __name__=="__main__": run(CONFIG)
