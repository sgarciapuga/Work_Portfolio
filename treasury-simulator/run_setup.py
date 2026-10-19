"""Set up the tsim schema in Neon and load the static data.

Run from the repository root:

    python treasury-simulator/run_setup.py --check       # validate the static CSVs only (no database)
    python treasury-simulator/run_setup.py --schema      # create the tsim schema and tables
    python treasury-simulator/run_setup.py --static      # upsert the static CSVs
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from tsim.static_data import load_static, summary, validate  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="validate the static CSVs only")
    parser.add_argument("--schema", action="store_true", help="create the tsim schema in Neon")
    parser.add_argument("--static", action="store_true", help="upsert the static CSVs into Neon")
    args = parser.parse_args()

    data = load_static()
    problems = validate(data)
    if problems:
        print("Static data problems:")
        for p in problems:
            print(" -", p)
        sys.exit(1)
    print("Static data OK:", summary(data))

    if args.schema or args.static:
        from tsim.db import create_schema, get_engine, load_static_to_db

        engine = get_engine()
        if args.schema:
            create_schema(engine)
            print("tsim schema created (or already there).")
        if args.static:
            print("Rows upserted:", load_static_to_db(engine, data))


if __name__ == "__main__":
    main()
