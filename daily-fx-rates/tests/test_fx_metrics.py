import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from datetime import date

from fx_metrics import (
    filter_period,
    moving_average,
    period_csv,
    period_summary,
    preset_start,
    priced_in,
    rebased,
    to_pairs,
)


def _rates(rows):
    """rows: (date, eur, gbp, flag) -> long fx_rates frame."""
    records = []
    for date, eur, gbp, flag in rows:
        records.append({"date": date, "currency": "EUR", "fx_to_usd": eur, "fx_quality_flag": flag})
        records.append({"date": date, "currency": "GBP", "fx_to_usd": gbp, "fx_quality_flag": flag})
        records.append({"date": date, "currency": "USD", "fx_to_usd": 1.0, "fx_quality_flag": "raw"})
    return pd.DataFrame(records)


# Thu, Fri market days, then a filled weekend.
RATES = _rates(
    [
        ("2026-10-01", 0.80, 0.75, "raw"),
        ("2026-10-02", 0.85, 0.80, "raw"),
        ("2026-10-03", 0.85, 0.80, "filled"),
        ("2026-10-04", 0.85, 0.80, "filled"),
    ]
)


class FxMetricsTests(unittest.TestCase):
    def test_pairs_are_inverted_and_crossed(self):
        pairs = to_pairs(RATES)
        first = pairs.iloc[0]
        self.assertAlmostEqual(first["GBP/USD"], 1 / 0.75)
        self.assertAlmostEqual(first["EUR/USD"], 1 / 0.80)
        self.assertAlmostEqual(first["GBP/EUR"], 0.80 / 0.75)
        self.assertEqual(pairs["is_raw"].tolist(), [True, True, False, False])

    def test_vs_previous_day_skips_filled_days(self):
        summary = period_summary(to_pairs(RATES))
        # Last market day (2 Oct) vs the one before (1 Oct), not Sun vs Sat (0%).
        self.assertAlmostEqual(summary.loc["GBP/USD", "vs_previous_day"], 0.75 / 0.80 - 1)

    def test_summary_uses_every_day_in_period(self):
        pairs = to_pairs(RATES)
        summary = period_summary(pairs)
        self.assertAlmostEqual(summary.loc["EUR/USD", "average"], pairs["EUR/USD"].mean())
        self.assertAlmostEqual(summary.loc["EUR/USD", "high"], 1 / 0.80)
        self.assertAlmostEqual(summary.loc["EUR/USD", "low"], 1 / 0.85)
        self.assertAlmostEqual(summary.loc["EUR/USD", "since_start"], 0.80 / 0.85 - 1)

    def test_high_and_low_dates_use_the_market_day(self):
        summary = period_summary(to_pairs(RATES))
        # EUR/USD is highest on 1 Oct and lowest from 2 Oct (carried over the weekend).
        self.assertEqual(summary.loc["EUR/USD", "high_date"], pd.Timestamp("2026-10-01"))
        self.assertEqual(summary.loc["EUR/USD", "low_date"], pd.Timestamp("2026-10-02"))

    def test_period_csv(self):
        lines = period_csv(to_pairs(RATES)).splitlines()
        self.assertEqual(lines[0], "date,GBP/USD,EUR/USD,GBP/EUR,rate_type")
        self.assertTrue(lines[1].startswith("2026-10-01,1.333333,1.25,"))
        self.assertTrue(lines[1].endswith(",market"))
        self.assertTrue(lines[-1].endswith(",filled"))
        self.assertEqual(len(lines), 5)

    def test_filter_period_is_inclusive(self):
        period = filter_period(to_pairs(RATES), "2026-10-02", "2026-10-03")
        self.assertEqual(len(period), 2)

    def test_rebased_starts_at_100(self):
        indexed = rebased(to_pairs(RATES))
        self.assertTrue((indexed.iloc[0] == 100).all())

    def test_priced_in_other_bases(self):
        pairs = to_pairs(RATES)
        in_gbp = priced_in(pairs, "GBP").iloc[0]
        in_eur = priced_in(pairs, "EUR").iloc[0]
        # 1 USD = 0.80 EUR = 0.75 GBP on 1 Oct.
        self.assertAlmostEqual(in_gbp["USD/GBP"], 0.75)
        self.assertAlmostEqual(in_gbp["EUR/GBP"], 0.75 / 0.80)
        self.assertAlmostEqual(in_eur["USD/EUR"], 0.80)
        self.assertAlmostEqual(in_eur["GBP/EUR"], pairs["GBP/EUR"].iloc[0])
        self.assertEqual(list(priced_in(pairs, "USD").columns), ["GBP/USD", "EUR/USD"])

    def test_preset_start(self):
        first, last = date(2026, 1, 1), date(2026, 10, 15)
        self.assertEqual(preset_start("1M", first, last), date(2026, 9, 15))
        self.assertEqual(preset_start("3M", first, last), date(2026, 7, 15))
        self.assertEqual(preset_start("YTD", first, last), date(2026, 1, 1))
        self.assertEqual(preset_start("All", first, last), first)
        # Never before the first day of data.
        self.assertEqual(preset_start("1Y", first, last), first)
        self.assertEqual(preset_start("1Y", date(2025, 1, 1), date(2026, 3, 31)), date(2025, 3, 31))
        self.assertEqual(preset_start("YTD", date(2025, 1, 1), date(2027, 2, 1)), date(2027, 1, 1))

    def test_moving_average_starts_with_first_value(self):
        series = pd.Series([1.0, 2.0, 3.0])
        self.assertEqual(moving_average(series, days=2).tolist(), [1.0, 1.5, 2.5])

    def test_duplicates_keep_last_row(self):
        rates = pd.concat([RATES, _rates([("2026-10-04", 0.90, 0.80, "raw")])])
        pairs = to_pairs(rates)
        self.assertEqual(len(pairs), 4)
        self.assertAlmostEqual(pairs["EUR/USD"].iloc[-1], 1 / 0.90)


if __name__ == "__main__":
    unittest.main()
