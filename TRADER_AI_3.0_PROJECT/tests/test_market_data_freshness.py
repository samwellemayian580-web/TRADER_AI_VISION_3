import unittest

from data.market_data import (
    TIMEFRAMES,
    FRESHNESS_LIMIT_SECONDS,
    _is_stale,
)


class MarketDataFreshnessTests(unittest.TestCase):

    def test_all_nine_timeframes_have_freshness_limits(self):
        self.assertEqual(set(TIMEFRAMES), set(FRESHNESS_LIMIT_SECONDS))

    def test_data_at_limit_is_not_stale(self):
        for timeframe, limit in FRESHNESS_LIMIT_SECONDS.items():
            with self.subTest(timeframe=timeframe):
                self.assertFalse(_is_stale(timeframe, limit))

    def test_data_over_limit_is_stale(self):
        for timeframe, limit in FRESHNESS_LIMIT_SECONDS.items():
            with self.subTest(timeframe=timeframe):
                self.assertTrue(_is_stale(timeframe, limit + 0.1))

    def test_recent_m1_feed_sample_is_allowed(self):
        self.assertFalse(_is_stale("M1", 150.8))

    def test_old_m1_data_is_blocked(self):
        self.assertTrue(_is_stale("M1", 181))

    def test_old_m5_data_is_blocked(self):
        self.assertTrue(_is_stale("M5", 601))


if __name__ == "__main__":
    unittest.main()
