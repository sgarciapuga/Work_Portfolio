from pathlib import Path
import sys

project_root = Path(__file__).resolve().parent
repo_root = project_root.parent
sys.path.extend([
    str(repo_root),
    str(project_root / "src"),
])

from simulate_pipeline import simulate_pipeline


if __name__ == "__main__":
    print("Running treasury cashflow simulation from:", project_root)
    simulate_pipeline()
