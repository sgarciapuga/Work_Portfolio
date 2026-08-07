import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from generate_fx_portfolio import generate_fx_portfolio
from generate_limits import build_limit_schedule


class PortfolioDateFilterTests(unittest.TestCase):
    def test_report_date_excludes_positions_maturing_today(self):
        df = generate_fx_portfolio(end_date="2026-08-05", seed=42)
        self.assertFalse(((df["report_date"] == df["value_date"]).any()))

    def test_value_dates_can_extend_beyond_report_horizon(self):
        df = generate_fx_portfolio(end_date="2026-08-05", seed=42)
        value_dates = pd.to_datetime(df["value_date"])
        report_end = pd.Timestamp("2026-08-05")
        self.assertTrue((value_dates > report_end).any())

    def test_daily_exposure_never_exceeds_bank_limit(self):
        end_date = "2026-08-05"
        df = generate_fx_portfolio(end_date=end_date, seed=42)
        limits = build_limit_schedule(end_date=end_date, seed=42)

        daily_exposure = (
            df.groupby(["report_date", "bank_id"], as_index=False)["trade_size_usd"]
            .sum()
        )

        breaches = []
        for _, row in daily_exposure.iterrows():
            report_date = row["report_date"]
            bank_id = row["bank_id"]
            exposure = float(row["trade_size_usd"])
            limit = float(limits[report_date][bank_id])
            if exposure > limit + 0.01:
                breaches.append((report_date, bank_id, exposure, limit))

        self.assertEqual([], breaches)


if __name__ == "__main__":
    unittest.main()
