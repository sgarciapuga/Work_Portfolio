import sys
import os
import tempfile
import pandas as pd
from pathlib import Path

# Add src to sys.path
sys.path.append(os.path.join(os.getcwd(), 'fx-prime-brokerage-collateral', 'src'))

from generate_fx_datasets import _last_date_in_csv, _incremental_slice, _write_csv

results = {}

# 1. _last_date_in_csv returns None for a nonexistent file.
nonexistent = "nonexistent_file_xyz_123.csv"
last_date_none = _last_date_in_csv(nonexistent, 'report_date')
results['Check 1'] = last_date_none is None

# Create a temporary file path
with tempfile.TemporaryDirectory() as tmpdir:
    tmp_csv = os.path.join(tmpdir, "temp_test.csv")
    
    # 2. Create small pandas DataFrame with 'report_date' column of 3 dates (2026-01-01, 2026-01-02, 2026-01-03)
    # and write it via _write_csv(df, tmp_csv, None)
    dates3 = ['2026-01-01', '2026-01-02', '2026-01-03']
    df3 = pd.DataFrame({'report_date': dates3, 'value': [10, 20, 30]})
    _write_csv(df3, tmp_csv, None)
    
    # Verify file has all 3 rows of data (excluding header)
    written3 = pd.read_csv(tmp_csv)
    results['Check 2'] = len(written3) == 3 and list(written3['report_date']) == dates3
    
    # 3. Call _last_date_in_csv(tmp_csv, 'report_date') -- should return 2026-01-03 as a Timestamp.
    last_date = _last_date_in_csv(tmp_csv, 'report_date')
    is_timestamp = isinstance(last_date, pd.Timestamp)
    expected_timestamp = pd.Timestamp('2026-01-03')
    results['Check 3'] = is_timestamp and (last_date == expected_timestamp)
    
    # 4. Create a new 'full' DataFrame with 5 dates (2026-01-01 through 2026-01-05),
    # compute _incremental_slice(full_df, 'report_date', last_date) -- should return only rows for 01-04 and 01-05 (2 rows).
    dates5 = ['2026-01-01', '2026-01-02', '2026-01-03', '2026-01-04', '2026-01-05']
    df5 = pd.DataFrame({'report_date': dates5, 'value': [10, 20, 30, 40, 50]})
    incremental_df = _incremental_slice(df5, 'report_date', last_date)
    expected_dates_inc = ['2026-01-04', '2026-01-05']
    results['Check 4'] = len(incremental_df) == 2 and list(incremental_df['report_date']) == expected_dates_inc
    
    # 5. Call _write_csv(incremental_df, tmp_csv, last_date) -- verify file now has 5 total rows (3 original + 2 appended), with no duplicates.
    _write_csv(incremental_df, tmp_csv, last_date)
    written5 = pd.read_csv(tmp_csv)
    results['Check 5'] = len(written5) == 5 and list(written5['report_date']) == dates5

# Print output
for check, status in results.items():
    print(f"{check}: {'PASS' if status else 'FAIL'}")
