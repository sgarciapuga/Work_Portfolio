import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Load .env from repo root
repo_root = Path(__file__).resolve().parent.parent
load_dotenv(repo_root / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set in environment.")
    sys.exit(2)

try:
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        result = conn.execute(text("SELECT COUNT(*) FROM date_table"))
        count = result.scalar()
    print(f"date_table row count: {count}")
    if count is None:
        print("ERROR: could not retrieve count from date_table.")
        sys.exit(3)
except Exception as e:
    print(f"ERROR: failed to verify date_table: {e}")
    sys.exit(1)
