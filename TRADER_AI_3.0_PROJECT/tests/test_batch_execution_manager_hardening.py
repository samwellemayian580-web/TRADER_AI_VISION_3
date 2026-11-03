import unittest
from unittest.mock import patch

from risk.batch_execution_manager import BatchExecutionManager
from risk.risk_manager import RiskManager


class TestBatchExecutionManagerHardening(unittest.TestCase):
    def setUp(self):
        self.risk_manager = RiskManager(
            equity=500.0,
            risk_per_trade=1.0,
            max_risk_per_trade=10.0,
            max_total_risk=10.0,
            max_positions=5,
        )
        self.manager = BatchExecutionManager(self.risk_manager)

        self.batch = {
            "approved": True,
            "side": "BUY",
            "entry": 3000.0,
            "stop_loss": 2999.0,
            "order_count": 2,
            "orders": [
                {"lot": 0.02, "estimated_risk": 2.0},
                {"lot": 0.01, "estimated_risk": 3.0},
            ],
            "total_lot": 0.03,
            "total_estimated_risk": 5.0,
        }

    def test_reject_boolean_order_count(self):
        invalid = dict(self.batch, order_count=True)
        ok, _ = self.manager.create_batch(
            "setup-1", invalid, 3002.0
        )
        self.assertFalse(ok)
        self.assertEqual(len(self.risk_manager.positions), 0)

    def test_reject_string_order_count(self):
        invalid = dict(self.batch, order_count="2")
        ok, _ = self.manager.create_batch(
            "setup-1", invalid, 3002.0
        )
        self.assertFalse(ok)

    def test_reject_malformed_child_order(self):
        invalid = dict(self.batch)
        invalid["orders"] = [
            {"lot": 0.02, "estimated_risk": 2.0},
            "not-an-order",
        ]
        ok, _ = self.manager.create_batch(
            "setup-1", invalid, 3002.0
        )
        self.assertFalse(ok)
        self.assertEqual(len(self.risk_manager.positions), 0)

    def test_reject_mismatched_batch_risk_total(self):
        invalid = dict(self.batch, total_estimated_risk=4.0)
        ok, _ = self.manager.create_batch(
            "setup-1", invalid, 3002.0
        )
        self.assertFalse(ok)
        self.assertEqual(len(self.risk_manager.positions), 0)

    def test_reject_mismatched_batch_lot_total(self):
        invalid = dict(self.batch, total_lot=0.04)
        ok, _ = self.manager.create_batch(
            "setup-1", invalid, 3002.0
        )
        self.assertFalse(ok)
        self.assertEqual(len(self.risk_manager.positions), 0)

    def test_reject_batch_above_per_trade_risk_limit(self):
        invalid = {
            **self.batch,
            "orders": [
                {"lot": 0.02, "estimated_risk": 30.0},
                {"lot": 0.01, "estimated_risk": 25.0},
            ],
            "total_estimated_risk": 55.0,
        }
        ok, _ = self.manager.create_batch(
            "setup-1", invalid, 3002.0
        )
        self.assertFalse(ok)
        self.assertEqual(len(self.manager.setups), 0)
        self.assertEqual(len(self.risk_manager.positions), 0)

    def test_failed_final_order_risk_release_preserves_state(self):
        ok, msg = self.manager.create_batch(
            "setup-1", self.batch, 3002.0
        )
        self.assertTrue(ok, msg)

        ok, msg = self.manager.close_order(
            "setup-1", "setup-1-O001", 3001.0, "TEST_PARTIAL"
        )
        self.assertTrue(ok, msg)

        with patch.object(
            self.risk_manager,
            "close_position",
            return_value=(False, "simulated release failure"),
        ):
            ok, msg = self.manager.close_order(
                "setup-1", "setup-1-O002", 3001.0, "TEST_FINAL"
            )
            self.assertFalse(ok)
            self.assertIn("Risk release failed", msg)

        setup = self.manager.setups["setup-1"]
        self.assertEqual(setup["status"], "OPEN")
        self.assertEqual(
            setup["orders"]["setup-1-O001"]["status"], "CLOSED"
        )
        self.assertEqual(
            setup["orders"]["setup-1-O002"]["status"], "OPEN"
        )
        self.assertEqual(self.risk_manager.current_risk(), 5.0)

    def test_failed_batch_risk_release_preserves_state(self):
        ok, msg = self.manager.create_batch(
            "setup-1", self.batch, 3002.0
        )
        self.assertTrue(ok, msg)

        with patch.object(
            self.risk_manager,
            "close_position",
            return_value=(False, "simulated release failure"),
        ):
            ok, msg = self.manager.close_batch(
                "setup-1", 2999.0, "STOP_LOSS"
            )
            self.assertFalse(ok)
            self.assertIn("Risk release failed", msg)

        setup = self.manager.setups["setup-1"]
        self.assertEqual(setup["status"], "OPEN")
        self.assertTrue(
            all(
                order["status"] == "OPEN"
                for order in setup["orders"].values()
            )
        )
        self.assertEqual(self.risk_manager.current_risk(), 5.0)


if __name__ == "__main__":
    unittest.main()
