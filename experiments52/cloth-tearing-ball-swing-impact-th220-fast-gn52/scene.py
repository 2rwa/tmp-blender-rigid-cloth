from pathlib import Path
import sys
sys.path.insert(0,str(Path.cwd()))
from experiments52._shared.impact_tearing import run
CONFIG={
  "experiment": "cloth-tearing-ball-swing-impact-th220-fast-gn52",
  "pattern": "swing",
  "impact_z": 2.18,
  "tear_half_width": 0.22,
  "tear_slope": 0.34,
  "threshold": 2.2,
  "stretchiness": 0.05,
  "ball_radius": 0.45,
  "ball_start": [-1.75, -2.35, 1.62],
  "ball_impact": [0, -0.33, 2.18],
  "ball_end": [1.55, 1.2, 2.65],
  "impact_frame": 22,
  "end_frame": 39,
  "substeps": 16,
  "constraint_steps": 32,
  "ball_color": [0.92, 0.68, 0.05, 1],
}
if __name__=="__main__": run(CONFIG)
