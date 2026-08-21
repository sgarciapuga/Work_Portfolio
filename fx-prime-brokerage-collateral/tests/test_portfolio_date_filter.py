import sys
import tempfile
import unittest
import re
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from generate_fx_portfolio import generate_fx_portfolio
from generate_limits import build_limit_schedule
from generate_mtm_report import generate_mtm_report


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

    def test_weekly_trade_arrivals_are_bounded_and_not_fixed_daily(self):
        end_date = "2026-08-05"
        df = generate_fx_portfolio(end_date=end_date, seed=42)
        trades = df[["trade_id", "trade_date"]].drop_duplicates()
        weekly_counts = trades.groupby(
            pd.to_datetime(trades["trade_date"]).dt.to_period("W")
        ).size()

        self.assertTrue((weekly_counts <= 7).all())
        self.assertTrue((weekly_counts >= 0).all())
        self.assertGreater(weekly_counts.nunique(), 1)

    def test_trade_ids_are_unique_formatted_and_shared_by_legs(self):
        df = generate_fx_portfolio(end_date="2026-08-05", seed=42)
        trade_rows = df.drop_duplicates(subset=["trade_id", "trade_date", "type", "leg_id"])

        self.assertTrue(
            trade_rows["trade_id"].map(
                lambda value: bool(re.fullmatch(r"(?:SP|FW|SW)\d{8}\d{4}", value))
            ).all()
        )
        identity = trade_rows.groupby("trade_id").agg(
            trade_dates=("trade_date", "nunique"),
            trade_types=("type", "nunique"),
        )
        self.assertTrue((identity == 1).all().all())

        swap_ids = trade_rows.loc[trade_rows["type"] == "swap", "trade_id"]
        self.assertTrue(
            (trade_rows[trade_rows["trade_id"].isin(swap_ids)]
             .groupby("trade_id")["leg_id"].nunique() == 2).all()
        )

    def test_collateral_report_preserves_variation_margin_sign(self):
        portfolio = pd.DataFrame({
            "trade_date": ["2026-01-02", "2026-01-05"],
            "report_date": ["2026-01-02", "2026-01-05"],
            "trade_size_usd": [100_000, 100_000],
        })
        mtm = pd.DataFrame({
            "report_date": ["2026-01-02", "2026-01-05"],
            "pnl": [1_000, -1_000],
        })

        with tempfile.TemporaryDirectory() as output_dir:
            result = generate_mtm_report(
                portfolio_df=portfolio,
                mtm_df=mtm,
                end_date="2026-01-05",
                out_path=output_dir,
            )

        self.assertEqual(-5_000, result.loc[0, "initial_margin"])
        self.assertEqual(1_000, result.loc[0, "variation_margin"])
        self.assertEqual(-4_000, result.loc[0, "collateral_required"])
        self.assertEqual(-1_000, result.loc[1, "variation_margin"])
        self.assertEqual(-6_000, result.loc[1, "collateral_required"])

    def test_recall_does_not_leave_next_day_below_buffer(self):
        portfolio = pd.DataFrame({
            "trade_date": ["2026-01-02", "2026-01-05", "2026-01-06"],
            "report_date": ["2026-01-02", "2026-01-05", "2026-01-06"],
            "trade_size_usd": [1_000_000, 0, 4_000_000],
        })
        mtm = pd.DataFrame({
            "report_date": ["2026-01-02", "2026-01-05", "2026-01-06"],
            "pnl": [0, 0, 0],
        })

        with tempfile.TemporaryDirectory() as output_dir:
            result = generate_mtm_report(
                portfolio_df=portfolio,
                mtm_df=mtm,
                end_date="2026-01-06",
                out_path=output_dir,
            )

        self.assertEqual(550_000, result.loc[1, "collateral_posted"])
        self.assertEqual(550_000, result.loc[2, "collateral_posted"])
        self.assertLess(result.loc[2, "excess_deficit"], 500_000)

    def test_recall_requires_minimum_excess_above_buffer(self):
        portfolio = pd.DataFrame({
            "trade_date": ["2026-01-02", "2026-01-05", "2026-01-06"],
            "report_date": ["2026-01-02", "2026-01-05", "2026-01-06"],
            "trade_size_usd": [20_000_000, 19_980_000, 0],
        })
        mtm = pd.DataFrame({
            "report_date": ["2026-01-02", "2026-01-05", "2026-01-06"],
            "pnl": [0, 0, 0],
        })

        with tempfile.TemporaryDirectory() as output_dir:
            result = generate_mtm_report(
                portfolio_df=portfolio,
                mtm_df=mtm,
                end_date="2026-01-06",
                out_path=output_dir,
            )

        self.assertEqual(501_000, result.loc[1, "excess_deficit"])
        self.assertEqual(
            result.loc[1, "collateral_posted"],
            result.loc[2, "collateral_posted"],
        )


if __name__ == "__main__":
    unittest.main()
