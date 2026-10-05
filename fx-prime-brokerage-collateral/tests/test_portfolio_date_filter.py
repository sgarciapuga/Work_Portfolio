import sys
import tempfile
import unittest
import re
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from generate_fx_portfolio import generate_fx_portfolio
from generate_limits import build_limit_schedule
from generate_mtm_for_portfolio import generate_mtm_for_portfolio
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

    def test_recall_is_sized_from_current_day_only(self):
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

        # 01-05 COB: 550k posted, no exposure -> 50k above buffer, so recall 50k.
        # The bigger 01-06 exposure isn't known at 01-05 COB and must not block it.
        self.assertEqual(550_000, result.loc[1, "collateral_posted"])
        self.assertEqual(500_000, result.loc[2, "collateral_posted"])
        self.assertEqual(300_000, result.loc[2, "excess_deficit"])

    def test_recall_requires_minimum_excess_above_buffer(self):
        portfolio = pd.DataFrame({
            "trade_date": ["2026-01-02", "2026-01-05", "2026-01-06"],
            "report_date": ["2026-01-02", "2026-01-05", "2026-01-06"],
            "trade_size_usd": [10_000_000, 9_980_000, 0],
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

    def test_collateral_starts_at_initial_collateral(self):
        portfolio = pd.DataFrame({
            "trade_date": ["2026-01-02"],
            "report_date": ["2026-01-02"],
            "trade_size_usd": [1_000_000],
        })
        mtm = pd.DataFrame({"report_date": ["2026-01-02"], "pnl": [0]})

        with tempfile.TemporaryDirectory() as output_dir:
            result = generate_mtm_report(
                portfolio_df=portfolio, mtm_df=mtm, end_date="2026-01-02", out_path=output_dir
            )

        self.assertEqual(1_000_000, result.loc[0, "collateral_posted"])
        self.assertEqual(950_000, result.loc[0, "excess_deficit"])

    def test_swap_initial_margin_uses_far_leg_only(self):
        portfolio = pd.DataFrame({
            "trade_date": ["2026-01-02"] * 3,
            "report_date": ["2026-01-02"] * 3,
            "type": ["swap", "swap", "spot"],
            "leg_id": [1, 2, 1],
            "trade_size_usd": [1_000_000, 1_005_000, 500_000],
        })
        mtm = pd.DataFrame({"report_date": ["2026-01-02"], "pnl": [0]})

        with tempfile.TemporaryDirectory() as output_dir:
            result = generate_mtm_report(
                portfolio_df=portfolio, mtm_df=mtm, end_date="2026-01-02", out_path=output_dir
            )

        self.assertEqual(-75_250, result.loc[0, "initial_margin"])

    def test_swap_legs_differ_only_by_forward_points(self):
        df = generate_fx_portfolio(end_date="2026-08-05", seed=42)
        legs = (
            df[df["type"] == "swap"]
            .drop_duplicates(["trade_id", "bank_id", "leg_id"])
            .pivot(index=["trade_id", "bank_id"], columns="leg_id", values="trade_size_usd")
            .dropna()
        )
        self.assertGreater(len(legs), 0)
        ratio = legs[2] / legs[1]
        self.assertTrue(ratio.between(0.99, 1.01).all())

    def test_mtm_stops_before_value_date(self):
        portfolio = pd.DataFrame({
            "trade_id": ["SP202601050001"] * 2,
            "bank_id": ["bank_1"] * 2,
            "report_date": ["2026-01-05", "2026-01-06"],
            "trade_date": ["2026-01-05"] * 2,
            "value_date": ["2026-01-07"] * 2,
            "trade_size_usd": [1_000_000] * 2,
        })

        mtm = generate_mtm_for_portfolio(portfolio, end_date="2026-01-09")

        self.assertEqual(["2026-01-05", "2026-01-06"], mtm["report_date"].tolist())

    def test_split_trade_gets_mtm_for_each_bank(self):
        portfolio = pd.DataFrame({
            "trade_id": ["FW202601050001"] * 2,
            "bank_id": ["bank_1", "bank_2"],
            "report_date": ["2026-01-05"] * 2,
            "trade_date": ["2026-01-05"] * 2,
            "value_date": ["2026-02-05"] * 2,
            "trade_size_usd": [3_000_000, 1_000_000],
        })

        mtm = generate_mtm_for_portfolio(portfolio, end_date="2026-01-09")
        by_bank = {bank: rows.reset_index(drop=True) for bank, rows in mtm.groupby("bank_id")}

        self.assertEqual({"bank_1", "bank_2"}, set(by_bank))
        # same price path, P&L scaled by each bank's share
        pd.testing.assert_series_equal(by_bank["bank_1"]["mtm"], by_bank["bank_2"]["mtm"])
        self.assertAlmostEqual(
            by_bank["bank_1"]["pnl"].iloc[-1], 3 * by_bank["bank_2"]["pnl"].iloc[-1], delta=0.05
        )


class HistoryStabilityTests(unittest.TestCase):
    """Adding a day must not rewrite earlier days (the daily run only appends)."""

    DAY = "2026-08-05"       # a Wednesday, so the current week is still partial
    NEXT_DAY = "2026-08-06"

    @staticmethod
    def _generate(end_date):
        portfolio = generate_fx_portfolio(end_date=end_date, seed=42)
        mtm = generate_mtm_for_portfolio(portfolio.copy(), end_date=end_date)
        with tempfile.TemporaryDirectory() as output_dir:
            report = generate_mtm_report(
                portfolio_df=portfolio.copy(), mtm_df=mtm, end_date=end_date, out_path=output_dir
            )
        return portfolio, mtm, report

    @classmethod
    def setUpClass(cls):
        cls.before = cls._generate(cls.DAY)
        cls.after = cls._generate(cls.NEXT_DAY)

    def _assert_prefix_unchanged(self, before, after):
        before = before.astype({"report_date": str})
        after = after.astype({"report_date": str})
        after = after.loc[after["report_date"] <= self.DAY]
        self.assertGreater(len(before), 0)
        pd.testing.assert_frame_equal(before.reset_index(drop=True), after.reset_index(drop=True))

    def test_portfolio_history_is_stable(self):
        self._assert_prefix_unchanged(self.before[0], self.after[0])

    def test_mtm_history_is_stable(self):
        self._assert_prefix_unchanged(self.before[1], self.after[1])

    def test_collateral_report_history_is_stable(self):
        self._assert_prefix_unchanged(self.before[2], self.after[2])


if __name__ == "__main__":
    unittest.main()
