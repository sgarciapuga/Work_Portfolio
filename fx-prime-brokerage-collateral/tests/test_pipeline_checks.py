import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from generate_fx_datasets import (
    _check_history_unchanged,
    _incremental_slice,
    _last_date_in_csv,
    _write_csv,
)


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


class IncrementalWriteTests(unittest.TestCase):
    """The daily run appends only the days after the last date in each CSV."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.csv = Path(self.tmp.name) / "data.csv"
        self.dates = ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04", "2026-01-05"]

    def tearDown(self):
        self.tmp.cleanup()

    def _frame(self, n):
        return pd.DataFrame({"report_date": self.dates[:n], "value": [10 * (i + 1) for i in range(n)]})

    def test_last_date_is_none_without_a_file(self):
        self.assertIsNone(_last_date_in_csv(self.csv, "report_date"))

    def test_first_run_writes_every_row(self):
        _write_csv(self._frame(3), self.csv, None)
        self.assertEqual(self.dates[:3], pd.read_csv(self.csv)["report_date"].tolist())
        self.assertEqual(pd.Timestamp("2026-01-03"), _last_date_in_csv(self.csv, "report_date"))

    def test_next_run_appends_only_the_new_days(self):
        _write_csv(self._frame(3), self.csv, None)
        last_date = _last_date_in_csv(self.csv, "report_date")
        new_rows = _incremental_slice(self._frame(5), "report_date", last_date)
        self.assertEqual(self.dates[3:], new_rows["report_date"].tolist())

        _write_csv(new_rows, self.csv, last_date)
        written = pd.read_csv(self.csv)
        self.assertEqual(self.dates, written["report_date"].tolist())
        self.assertFalse(written.duplicated().any())

    def test_nothing_is_appended_when_there_are_no_new_days(self):
        _write_csv(self._frame(3), self.csv, None)
        last_date = _last_date_in_csv(self.csv, "report_date")
        _write_csv(_incremental_slice(self._frame(3), "report_date", last_date), self.csv, last_date)
        self.assertEqual(3, len(pd.read_csv(self.csv)))


if __name__ == "__main__":
    unittest.main()
