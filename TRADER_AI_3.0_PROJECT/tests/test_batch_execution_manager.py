import unittest

from risk.batch_execution_manager import BatchExecutionManager
from risk.risk_manager import RiskManager


class TestBatchExecutionManager(unittest.TestCase):
    def setUp(self):
        self.risk_manager = RiskManager(
            equity=500.0,
            risk_per_trade=1.0,
            max_risk_per_trade=10.0,
            max_total_risk=10.0,
            max_positions=5,
        )
        self.manager = BatchExecutionManager(self.risk_manager)
        self.buy_batch = {
            "approved": True,
            "side": "BUY",
            "entry": 3000.0,
            "stop_loss": 2999.0,
            "order_count": 3,
            "orders": [
                {"order_number": 1, "lot": 0.02, "estimated_risk": 2.0},
                {"order_number": 2, "lot": 0.02, "estimated_risk": 2.0},
                {"order_number": 3, "lot": 0.01, "estimated_risk": 1.0},
            ],
            "total_lot": 0.05,
            "total_estimated_risk": 5.0,
        }

    def test_create_batch_registers_one_setup_risk(self):
        ok, msg = self.manager.create_batch(
            "setup-1", self.buy_batch, target_price=3002.0
        )
        self.assertTrue(ok, msg)
        self.assertEqual(len(self.manager.setups), 1)
        self.assertEqual(len(self.risk_manager.positions), 1)
        self.assertEqual(self.risk_manager.positions["setup-1"], 5.0)
        self.assertEqual(len(self.manager.setups["setup-1"]["orders"]), 3)

    def test_child_orders_receive_unique_ids(self):
        ok, msg = self.manager.create_batch(
            "setup-1", self.buy_batch, target_price=3002.0
        )
        self.assertTrue(ok, msg)
        ids = [
            order["order_id"]
            for order in self.manager.setups["setup-1"]["orders"].values()
        ]
        self.assertEqual(len(ids), 3)
        self.assertEqual(len(set(ids)), 3)

    def test_partial_close_keeps_full_setup_risk_reserved(self):
        ok, msg = self.manager.create_batch(
            "setup-1", self.buy_batch, target_price=3002.0
        )
        self.assertTrue(ok, msg)

        ok, msg = self.manager.close_order(
            "setup-1", "setup-1-O001", 3001.0, "TAKE_PROFIT_1"
        )
        self.assertTrue(ok, msg)
        self.assertEqual(self.risk_manager.current_risk(), 5.0)
        self.assertEqual(len(self.risk_manager.positions), 1)
        self.assertEqual(
            self.manager.setups["setup-1"]["orders"]["setup-1-O001"]["status"],
            "CLOSED",
        )

    def test_closing_last_order_releases_setup_risk(self):
        ok, msg = self.manager.create_batch(
            "setup-1", self.buy_batch, target_price=3002.0
        )
        self.assertTrue(ok, msg)

        for order_id in ("setup-1-O001", "setup-1-O002", "setup-1-O003"):
            ok, msg = self.manager.close_order(
                "setup-1", order_id, 3001.0, "TAKE_PROFIT"
            )
            self.assertTrue(ok, msg)

        self.assertEqual(self.risk_manager.current_risk(), 0.0)
        self.assertEqual(len(self.risk_manager.positions), 0)
        self.assertEqual(self.manager.setups["setup-1"]["status"], "CLOSED")

    def test_close_batch_closes_all_orders_and_releases_risk(self):
        ok, msg = self.manager.create_batch(
            "setup-1", self.buy_batch, target_price=3002.0
        )
        self.assertTrue(ok, msg)

        ok, msg = self.manager.close_batch("setup-1", 2999.0, "STOP_LOSS")
        self.assertTrue(ok, msg)

        setup = self.manager.setups["setup-1"]
        self.assertEqual(setup["status"], "CLOSED")
        self.assertTrue(
            all(o["status"] == "CLOSED" for o in setup["orders"].values())
        )
        self.assertEqual(self.risk_manager.current_risk(), 0.0)

    def test_reject_duplicate_setup_id(self):
        ok, msg = self.manager.create_batch(
            "setup-1", self.buy_batch, target_price=3002.0
        )
        self.assertTrue(ok, msg)

        ok, _ = self.manager.create_batch(
            "setup-1", self.buy_batch, target_price=3002.0
        )
        self.assertFalse(ok)
        self.assertEqual(len(self.risk_manager.positions), 1)

    def test_reject_unapproved_batch(self):
        invalid = dict(self.buy_batch, approved=False)
        ok, _ = self.manager.create_batch(
            "setup-1", invalid, target_price=3002.0
        )
        self.assertFalse(ok)
        self.assertEqual(len(self.manager.setups), 0)
        self.assertEqual(len(self.risk_manager.positions), 0)

    def test_reject_wrong_buy_target_direction(self):
        ok, _ = self.manager.create_batch(
            "setup-1", self.buy_batch, target_price=2998.0
        )
        self.assertFalse(ok)
        self.assertEqual(len(self.risk_manager.positions), 0)

    def test_sell_batch_uses_sell_target_direction(self):
        sell = dict(
            self.buy_batch,
            side="SELL",
            entry=3000.0,
            stop_loss=3001.0,
        )
        ok, msg = self.manager.create_batch(
            "sell-1", sell, target_price=2998.0
        )
        self.assertTrue(ok, msg)
        self.assertEqual(self.manager.setups["sell-1"]["side"], "SELL")


if __name__ == "__main__":
    unittest.main()
