import unittest
from types import SimpleNamespace

from backtesting.multi_timeframe_backtester import MultiTimeframeBacktester


class TestMultiTimeframeBacktester(unittest.TestCase):

    def test_repeated_runs_reset_all_run_state(self):
        bot = MultiTimeframeBacktester(starting_balance=100.0)

        # Supply a tiny mock dataset; no external data is needed.
        timestamps = list(range(60))

        bot.adapter = SimpleNamespace(
            close_times={
                "M5": timestamps,
                "M15": timestamps,
                "H1": timestamps,
                "H4": timestamps,
            },
            data={
                "M5": [{
                    "open": 2500.0,
                    "high": 2501.0,
                    "low": 2499.0,
                    "close": 2500.5,
                }]
            },
            get_decision_times=lambda: [59],
        )

        for run_number in range(2):
            # Simulate leftover state from a previous run.
            bot.balance = 50.0
            bot.trades = [{"net_pnl": -50.0}]
            bot.equity_curve = [100.0, 50.0]
            bot.position = {"side": "BUY"}
            bot.pending_signal = {"side": "SELL"}

            report = bot.run(strategy="SCALPING", max_decisions=1)

            self.assertEqual(bot.balance, 100.0)
            self.assertEqual(bot.trades, [])
            self.assertEqual(bot.equity_curve, [100.0])
            self.assertIsNone(bot.position)
            self.assertIsNone(bot.pending_signal)

            self.assertEqual(report["starting_balance"], 100.0)
            self.assertEqual(report["ending_balance"], 100.0)
            self.assertEqual(report["total_trades"], 0)


if __name__ == "__main__":
    unittest.main()
