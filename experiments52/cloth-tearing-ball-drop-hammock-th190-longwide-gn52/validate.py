from pathlib import Path
import sys
sys.path.insert(0,str(Path.cwd()))
from experiments52._shared.validate_impact import validate
if __name__=="__main__": validate("cloth-tearing-ball-drop-hammock-th190-longwide-gn52")
