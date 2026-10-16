import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from fx_metrics import period_summary
from story import against_dollar, gbp_eur_position, headline, last_market_day, period_story


def _pairs(gbpusd, eurusd, is_raw=None, start="2026-10-01"):
    """Pairs frame from GBP/USD and EUR/USD levels (GBP/EUR is derived)."""
    index = pd.date_range(start, periods=len(gbpusd), freq="D")
    pairs = pd.DataFrame({"GBP/USD": gbpusd, "EUR/USD": eurusd}, index=index)
    pairs["GBP/EUR"] = pairs["GBP/USD"] / pairs["EUR/USD"]
    pairs["is_raw"] = is_raw if is_raw is not None else [True] * len(gbpusd)
    return pairs


class StoryTests(unittest.TestCase):
    def test_headline_names_the_winner(self):
        up = _pairs([1.30, 1.31], [1.10, 1.09])  # pound up, euro down
        self.assertEqual(headline(period_summary(up), up.index[0]), "The pound has gained on the euro since 1 Oct")
        down = _pairs([1.30, 1.29], [1.10, 1.11])
        self.assertEqual(headline(period_summary(down), down.index[0]), "The euro has gained on the pound since 1 Oct")
        level = _pairs([1.30, 1.30], [1.10, 1.10])
        self.assertEqual(headline(period_summary(level), level.index[0]), "The pound and the euro are level since 1 Oct")

    def test_against_dollar_wording(self):
        both_down = period_summary(_pairs([1.30, 1.28], [1.10, 1.05]))
        self.assertEqual(
            against_dollar(both_down),
            "Both lost ground against the dollar: the pound -1.54% and the euro -4.55%.",
        )
        both_up = period_summary(_pairs([1.30, 1.32], [1.10, 1.12]))
        self.assertTrue(against_dollar(both_up).startswith("Both gained against the dollar"))
        mixed = period_summary(_pairs([1.30, 1.32], [1.10, 1.09]))
        self.assertEqual(
            against_dollar(mixed),
            "Against the dollar, the pound rose +1.54% while the euro fell -0.91%.",
        )

    def test_gbp_eur_position(self):
        near_high = _pairs([1.30, 1.28, 1.32], [1.10, 1.10, 1.10])
        text = gbp_eur_position(near_high, period_summary(near_high))
        self.assertIn("close to its period high of 1.2000 on 3 Oct", text)
        self.assertIn("above its 30-day average", text)
        # Just below the high but in the top 10% of the period's range still reads as close to it.
        top_of_range = _pairs([1.25, 1.35, 1.345], [1.10, 1.10, 1.10])
        self.assertIn("close to its period high of 1.2273 on 2 Oct",
                      gbp_eur_position(top_of_range, period_summary(top_of_range)))
        middle = _pairs([1.30, 1.34, 1.28, 1.31], [1.10, 1.10, 1.10, 1.10])
        text = gbp_eur_position(middle, period_summary(middle))
        self.assertIn("between its low of 1.1636 (3 Oct) and high of 1.2182 (2 Oct)", text)

    def test_last_market_day_skips_the_weekend(self):
        # Thu 1 Oct, Fri 2 Oct market days; Sat 3 Oct filled.
        pairs = _pairs([1.30, 1.31, 1.31], [1.10, 1.10, 1.10], is_raw=[True, True, False])
        text = last_market_day(pairs, period_summary(pairs))
        self.assertTrue(text.startswith("On Fri 2 Oct, the last market day, GBP/USD +0.77%"))

    def test_story_uses_the_formatter(self):
        pairs = _pairs([1.30, 1.31], [1.10, 1.09])
        title, sentences = period_story(pairs, period_summary(pairs), fmt=lambda c: "[x]")
        self.assertTrue(title)
        self.assertEqual(len(sentences), 3)
        self.assertTrue(all("[x]" in s for s in sentences))


if __name__ == "__main__":
    unittest.main()
