import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from create_date_table import START_DATE, build_date_table, target_end_date

COLUMNS = [
    "calendar_date", "year", "quarter", "month", "month_name", "day", "day_of_week", "day_name",
    "weekday", "is_weekend", "is_month_start", "is_month_end", "week_num", "year_month",
    "year_quarter", "iso_week", "iso_year",
]


def _row(day: date) -> dict:
    df = build_date_table(day, day)
    return df.iloc[0].to_dict()


class BuildDateTableTests(unittest.TestCase):
    def test_columns_match_table_schema(self):
        df = build_date_table(date(2026, 1, 1), date(2026, 1, 31))
        self.assertEqual(list(df.columns), COLUMNS)

    def test_one_row_per_day_with_no_gaps(self):
        df = build_date_table(date(2024, 1, 1), date(2024, 12, 31))
        self.assertEqual(len(df), 366)
        self.assertTrue(df["calendar_date"].is_unique)
        self.assertEqual(df["calendar_date"].iloc[0], date(2024, 1, 1))
        self.assertEqual(df["calendar_date"].iloc[-1], date(2024, 12, 31))

    def test_calendar_attributes(self):
        row = _row(date(2026, 10, 21))  # a Wednesday
        self.assertEqual(row["calendar_date"], date(2026, 10, 21))
        self.assertEqual((row["year"], row["quarter"], row["month"], row["day"]), (2026, 4, 10, 21))
        self.assertEqual(row["month_name"], "October")
        self.assertEqual(row["day_name"], "Wednesday")
        self.assertEqual(row["day_of_week"], 3)
        self.assertEqual(row["weekday"], 2)
        self.assertFalse(row["is_weekend"])
        self.assertEqual(row["year_month"], "2026-10")
        self.assertEqual(row["year_quarter"], "2026-Q4")

    def test_weekend_flags_and_day_numbers(self):
        saturday, sunday = _row(date(2026, 10, 24)), _row(date(2026, 10, 25))
        self.assertTrue(saturday["is_weekend"])
        self.assertTrue(sunday["is_weekend"])
        self.assertEqual((saturday["day_of_week"], saturday["weekday"]), (6, 5))
        self.assertEqual((sunday["day_of_week"], sunday["weekday"]), (7, 6))

    def test_month_start_and_end_including_leap_day(self):
        self.assertTrue(_row(date(2024, 2, 29))["is_month_end"])
        self.assertFalse(_row(date(2024, 2, 28))["is_month_end"])
        self.assertTrue(_row(date(2025, 2, 28))["is_month_end"])
        self.assertTrue(_row(date(2025, 3, 1))["is_month_start"])
        self.assertFalse(_row(date(2025, 3, 2))["is_month_start"])

    def test_iso_week_and_year_at_year_boundaries(self):
        # 1 Jan 2027 is a Friday, so it belongs to ISO week 53 of 2026.
        row = _row(date(2027, 1, 1))
        self.assertEqual((row["year"], row["iso_year"], row["iso_week"], row["week_num"]), (2027, 2026, 53, 53))
        # 30 Dec 2024 is a Monday, so it opens ISO week 1 of 2025.
        row = _row(date(2024, 12, 30))
        self.assertEqual((row["year"], row["iso_year"], row["iso_week"]), (2024, 2025, 1))


class CoverageTests(unittest.TestCase):
    def test_target_end_date_is_end_of_next_year(self):
        self.assertEqual(target_end_date(date(2026, 1, 1)), date(2027, 12, 31))
        self.assertEqual(target_end_date(date(2026, 12, 31)), date(2027, 12, 31))

    def test_start_date_covers_fk_tables(self):
        # fx_rates and the treasury simulator backfill start on 1 Jan 2025.
        self.assertLessEqual(START_DATE, date(2025, 1, 1))


if __name__ == "__main__":
    unittest.main()
