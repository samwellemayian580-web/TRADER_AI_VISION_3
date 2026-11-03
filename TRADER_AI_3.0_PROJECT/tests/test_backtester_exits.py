import unittest

from backtesting.multi_timeframe_backtester import MultiTimeframeBacktester
from risk.risk_manager import RiskManager


class TestBacktesterExits(unittest.TestCase):

    def make_bot(self, side="BUY"):
        bot = MultiTimeframeBacktester.__new__(MultiTimeframeBacktester)

        bot.balance = 100.0
        bot.spread_price = 0.0
        bot.slippage_price = 0.0
        bot.commission_per_trade = 0.0
        bot.trades = []
        bot.equity_curve = [100.0]
        bot.risk_manager = RiskManager(
            equity=100.0,
            risk_per_trade=1.0,
            max_risk_per_trade=10.0,
            max_total_risk=10.0,
            max_positions=5,
        )
        approved, message = bot.risk_manager.approve_position(
            "test-position", 10.0
        )
        if not approved:
            raise RuntimeError(message)

        bot.position = {
            "side": side,
            "entry": 100.0,
            "stop": 95.0 if side == "BUY" else 105.0,
            "target": 110.0 if side == "BUY" else 90.0,
            "distance": 5.0,
            "risk_cash": 10.0,
            "risk_id": "test-position",
            "signal_time": "test",
            "analysis": {},
        }

        return bot

    def test_buy_gap_fills_at_open(self):
        bot = self.make_bot("BUY")

        bot._check_exit({
            "open": 90.0,
            "high": 92.0,
            "low": 89.0,
            "close": 91.0,
        }, 1)

        trade = bot.trades[0]
        self.assertEqual(trade["exit"], 90.0)
        self.assertEqual(trade["exit_reason"], "STOP_LOSS_GAP")
        self.assertEqual(trade["net_pnl"], -20.0)

    def test_sell_gap_fills_at_open(self):
        bot = self.make_bot("SELL")

        bot._check_exit({
            "open": 110.0,
            "high": 111.0,
            "low": 108.0,
            "close": 109.0,
        }, 1)

        trade = bot.trades[0]
        self.assertEqual(trade["exit"], 110.0)
        self.assertEqual(trade["exit_reason"], "STOP_LOSS_GAP")
        self.assertEqual(trade["net_pnl"], -20.0)

    def test_normal_buy_stop_uses_stop_price(self):
        bot = self.make_bot("BUY")

        bot._check_exit({
            "open": 100.0,
            "high": 103.0,
            "low": 94.0,
            "close": 98.0,
        }, 1)

        trade = bot.trades[0]
        self.assertEqual(trade["exit"], 95.0)
        self.assertEqual(trade["exit_reason"], "STOP_LOSS")

    def test_stop_wins_when_stop_and_target_both_hit(self):
        bot = self.make_bot("BUY")

        bot._check_exit({
            "open": 100.0,
            "high": 111.0,
            "low": 94.0,
            "close": 105.0,
        }, 1)

        trade = bot.trades[0]
        self.assertEqual(trade["exit"], 95.0)
        self.assertEqual(trade["exit_reason"], "STOP_LOSS")


    def test_entry_reserves_correct_risk(self):
        bot = MultiTimeframeBacktester.__new__(MultiTimeframeBacktester)
        bot.balance = 100.0
        bot.risk_percent = 1.0
        bot.atr_stop_multiple = 1.5
        bot.reward_ratio = 2.0
        bot.spread_price = 0.0
        bot.slippage_price = 0.0
        bot.risk_manager = RiskManager(equity=100.0)

        entered = bot._enter_position(
            {"open": 100.0},
            {
                "side": "BUY",
                "atr": 2.0,
                "signal_time": "test",
                "analysis": {},
            },
            1,
        )

        self.assertTrue(entered)
        self.assertAlmostEqual(bot.position["risk_cash"], 1.0)
        self.assertAlmostEqual(bot.risk_manager.current_risk(), 1.0)
        self.assertEqual(bot.risk_manager.status()["open_positions"], 1)

    def test_exit_releases_risk_and_updates_equity(self):
        bot = self.make_bot("BUY")

        bot._check_exit({
            "open": 100.0,
            "high": 103.0,
            "low": 94.0,
            "close": 98.0,
        }, 1)

        status = bot.risk_manager.status()
        self.assertEqual(status["open_positions"], 0)
        self.assertAlmostEqual(status["current_open_risk"], 0.0)
        self.assertAlmostEqual(status["equity"], bot.balance)
        self.assertAlmostEqual(bot.balance, 90.0)


    def test_entry_rejected_when_combined_risk_is_full(self):
        bot = MultiTimeframeBacktester.__new__(MultiTimeframeBacktester)
        bot.balance = 100.0
        bot.risk_percent = 1.0
        bot.atr_stop_multiple = 1.5
        bot.reward_ratio = 2.0
        bot.spread_price = 0.0
        bot.slippage_price = 0.0
        bot.position = None
        bot.risk_manager = RiskManager(equity=100.0)

        reserved = bot.risk_manager.approve_position(
            "existing-position", 10.0
        )
        self.assertTrue(reserved)

        entered = bot._enter_position(
            {"open": 100.0},
            {
                "side": "BUY",
                "atr": 2.0,
                "signal_time": "test",
                "analysis": {},
            },
            1,
        )

        self.assertFalse(entered)
        self.assertIsNone(bot.position)
        self.assertAlmostEqual(bot.risk_manager.current_risk(), 10.0)
        self.assertEqual(bot.risk_manager.status()["open_positions"], 1)


if __name__ == "__main__":
    unittest.main()
