import sys
from pathlib import Path

# Make `cef_tracker` importable when running `pytest` from the package/ dir.
sys.path.insert(0, str(Path(__file__).parent.parent))
