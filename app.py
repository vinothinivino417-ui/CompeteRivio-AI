"""Standard entry point for the complete CompeteRivio dashboard."""
from pathlib import Path
import runpy

runpy.run_path(str(Path(__file__).with_name("dashboard_preview.py")), run_name="__main__")
