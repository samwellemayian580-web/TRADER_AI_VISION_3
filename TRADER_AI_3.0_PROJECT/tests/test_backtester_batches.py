import unittest
from unittest.mock import patch

from backtesting.multi_timeframe_backtester import MultiTimeframeBacktester


class TestBacktesterBatches(unittest.TestCase):

    def setUp(self):
        with patch(
            "backtesting.multi_timeframe_backtester.HistoricalDataAdapter"
        ), patch(
            "backtesting.multi_timeframe_backtester.MultiTimeframeAnalyzer"
        ):
            self.backtester = MultiTimeframeBacktester(
                starting_balance=1000.0,
                risk_percent=1.0,
                reward_ratio=2.0,
                atr_stop_multiple=1.5,
                contract_size=100.0,
                account_currency_per_usd=1.0,
            )

        self.signal = {
            "side": "BUY",
            "atr": 0.5,
            "signal_time": "2026-11-01T10:00:00",
            "analysis": {"decision": "BUY_SETUP"},
        }

        self.candle = {"open": 3000.0}

    def create_batch(self):
        created = self.backtester._enter_batch_position(
            self.candle,
            self.signal,
            100,
        )
        self.assertTrue(created)

        self.assertEqual(len(self.backtester.batch_positions), 1)

        setup_id = next(iter(self.backtester.batch_positions))
        setup = self.backtester.batch_manager.setups[setup_id]

        return setup_id, setup

    def get_orders(self, setup):
        return list(setup["orders"].values())

    def test_signal_creates_one_batch_setup(self):
        setup_id, setup = self.create_batch()

        self.assertEqual(setup["status"], "OPEN")
        self.assertEqual(setup["side"], "BUY")
        self.assertEqual(len(self.backtester.risk_manager.positions), 1)
        self.assertGreater(len(setup["orders"]), 1)

    def test_child_orders_receive_unique_ids(self):
        setup_id, setup = self.create_batch()

        orders = self.get_orders(setup)
        order_ids = [order["order_id"] for order in orders]

        self.assertEqual(len(order_ids), len(set(order_ids)))
        self.assertTrue(all(order_ids))

    def test_partial_close_keeps_full_setup_risk_reserved(self):
        setup_id, setup = self.create_batch()

        original_risk = self.backtester.risk_manager.current_risk()
        first_order = self.get_orders(setup)[0]

        closed = self.backtester._close_batch_order(
            setup_id,
            first_order["order_id"],
            setup["entry"],
            "TEST_PARTIAL",
            101,
        )

        self.assertTrue(closed)
        self.assertEqual(first_order["status"], "CLOSED")
        self.assertEqual(setup["status"], "OPEN")

        self.assertAlmostEqual(
            self.backtester.risk_manager.current_risk(),
            original_risk,
        )
        self.assertIn(setup_id, self.backtester.batch_positions)

    def test_final_child_close_releases_setup_risk(self):
        setup_id, setup = self.create_batch()
        orders = self.get_orders(setup)

        for order in orders:
            closed = self.backtester._close_batch_order(
                setup_id,
                order["order_id"],
                setup["entry"],
                "TEST_CLOSE",
                102,
            )
            self.assertTrue(closed)

        self.assertEqual(setup["status"], "CLOSED")
        self.assertEqual(self.backtester.risk_manager.current_risk(), 0)
        self.assertEqual(len(self.backtester.risk_manager.positions), 0)
        self.assertNotIn(setup_id, self.backtester.batch_positions)
        self.assertEqual(len(self.backtester.trades), len(orders))

    def test_batch_stop_loss_closes_all_children(self):
        setup_id, setup = self.create_batch()

        candle = {
            "open": setup["entry"],
            "high": setup["entry"] + 0.1,
            "low": setup["stop_loss"] - 0.1,
        }

        closed = self.backtester._check_batch_exits(candle, 103)

        self.assertTrue(closed)
        self.assertEqual(setup["status"], "CLOSED")
        self.assertEqual(len(self.backtester.trades), len(setup["orders"]))

        self.assertTrue(
            all(
                trade["exit_reason"] == "STOP_LOSS"
                for trade in self.backtester.trades
            )
        )
        self.assertEqual(self.backtester.risk_manager.current_risk(), 0)

    def test_batch_take_profit_closes_all_children(self):
        setup_id, setup = self.create_batch()

        candle = {
            "open": setup["entry"],
            "high": setup["target_price"] + 0.1,
            "low": setup["entry"] - 0.1,
        }

        closed = self.backtester._check_batch_exits(candle, 104)

        self.assertTrue(closed)
        self.assertEqual(setup["status"], "CLOSED")
        self.assertEqual(len(self.backtester.trades), len(setup["orders"]))

        self.assertTrue(
            all(
                trade["exit_reason"] == "TAKE_PROFIT"
                for trade in self.backtester.trades
            )
        )
        self.assertEqual(self.backtester.risk_manager.current_risk(), 0)


if __name__ == "__main__":
    unittest.main()
