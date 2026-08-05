from pathlib import Path
import sys

repo_root = Path(__file__).resolve().parent
sys.path.extend([
    str(repo_root / "utils"),
    str(repo_root / "treasury-cashflow-simulation" / "src"),
])

from simulate_pipeline import simulate_pipeline

if __name__ == "__main__":
    print("Running treasury cashflow simulation from:", repo_root)
    simulate_pipeline()
