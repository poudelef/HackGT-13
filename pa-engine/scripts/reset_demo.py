"""Reset the local database and load the fictional sample library."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from synth.bootstrap import bootstrap_demo

if __name__ == "__main__":
    print(bootstrap_demo(force=True))
