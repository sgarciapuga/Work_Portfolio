import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from create_date_table import START_DATE, TABLE_NAME, target_end_date

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
        result = conn.execute(
            text(f"SELECT COUNT(*), MIN(calendar_date), MAX(calendar_date) FROM {TABLE_NAME}")
        )
        count, min_date, max_date = result.one()
except Exception as e:
    print(f"ERROR: failed to verify {TABLE_NAME}: {e}")
    sys.exit(1)

print(f"{TABLE_NAME}: {count} rows from {min_date} to {max_date}")

# Tables with a foreign key to date_table need every day from START_DATE up to
# the end of next year, with no gaps (calendar_date is the primary key, so
# count == days in range means no gaps).
end_date = target_end_date()
problems = []
if count == 0:
    problems.append("table is empty")
else:
    if min_date > START_DATE:
        problems.append(f"starts on {min_date}, expected {START_DATE} or earlier")
    if max_date < end_date:
        problems.append(f"ends on {max_date}, expected {end_date} or later")
    expected_rows = (max_date - min_date).days + 1
    if count != expected_rows:
        problems.append(f"{expected_rows - count} missing dates between {min_date} and {max_date}")

if problems:
    for problem in problems:
        print(f"ERROR: {problem}")
    sys.exit(3)
