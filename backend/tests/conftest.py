import os
import sys

# Make the backend/ package importable (dead_cta_detector, checker, models …)
# regardless of pytest's rootdir when run as `pytest tests/` from backend/.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
