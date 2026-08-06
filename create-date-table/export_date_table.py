import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import pandas as pd
from sqlalchemy import create_engine, text

# Load .env from repo root
repo_root = Path(__file__).resolve().parent.parent
load_dotenv(repo_root / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set in environment.")
    sys.exit(2)

out_dir = repo_root / "create-date-table" / "data"
out_dir.mkdir(parents=True, exist_ok=True)
out_file = out_dir / "date_table.csv"

try:
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        df = pd.read_sql(text("SELECT * FROM date_table ORDER BY calendar_date"), conn)
    df.to_csv(out_file, index=False)
    print(f"Exported date_table to {out_file}")
except Exception as e:
    print(f"ERROR: failed to export date_table: {e}")
    sys.exit(1)
