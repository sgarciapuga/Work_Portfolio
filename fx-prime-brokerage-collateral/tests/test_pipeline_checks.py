import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from generate_fx_datasets import _check_history_unchanged


class HistoryCheckTests(unittest.TestCase):
    def setUp(self):
        self.frame = pd.DataFrame({
            "report_date": ["2026-10-01", "2026-10-02", "2026-10-02"],
            "trade_id": ["A", "A", "B"],
            "pnl": [1.5, 2.25, -3.0],
        })
        self.tmp = tempfile.TemporaryDirectory()
        self.csv = Path(self.tmp.name) / "data.csv"
        self.frame.to_csv(self.csv, index=False)
        self.last_date = pd.Timestamp("2026-10-02")

    def tearDown(self):
        self.tmp.cleanup()

    def test_passes_when_regenerated_rows_match(self):
        regenerated = self.frame.iloc[::-1].copy()  # row order doesn't matter
        regenerated["report_date"] = pd.to_datetime(regenerated["report_date"])
        _check_history_unchanged(regenerated, self.csv, "report_date", self.last_date)

    def test_fails_when_regenerated_rows_differ(self):
        regenerated = self.frame.copy()
        regenerated.loc[2, "pnl"] = -3.01
        with self.assertRaises(RuntimeError):
            _check_history_unchanged(regenerated, self.csv, "report_date", self.last_date)

    def test_fails_when_a_row_disappears(self):
        regenerated = self.frame.iloc[:2].copy()
        with self.assertRaises(RuntimeError):
            _check_history_unchanged(regenerated, self.csv, "report_date", self.last_date)


if __name__ == "__main__":
    unittest.main()
