from pathlib import Path
import sys
sys.path.insert(0,str(Path.cwd()))
from experiments52._shared.impact_tearing import run
CONFIG={
  "experiment": "cloth-tearing-ball-drop-hammock-th160-fastball-gn52",
  "pattern": "hammock",
  "tear_radius": 0.95,
  "threshold": 1.6,
  "stretchiness": 0.055,
  "ball_radius": 0.52,
  "ball_start": [0, 0, 4.7],
  "ball_impact": [0, 0, 2.62],
  "ball_end": [0, 0, 0.75],
  "impact_frame": 24,
  "end_frame": 42,
  "substeps": 16,
  "constraint_steps": 34,
  "mass": 0.72,
  "ball_color": [0.62, 0.12, 0.78, 1],
}
if __name__=="__main__": run(CONFIG)
