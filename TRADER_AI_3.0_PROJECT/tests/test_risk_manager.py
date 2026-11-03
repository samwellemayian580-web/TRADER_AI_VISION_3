import unittest

from risk.risk_manager import RiskManager


class TestRiskManager(unittest.TestCase):

    def setUp(self):
        self.risk = RiskManager(equity=100.0)

    def test_default_risk_amount(self):
        self.assertAlmostEqual(self.risk.risk_amount(), 1.0)

    def test_maximum_trade_risk(self):
        self.assertAlmostEqual(self.risk.max_trade_risk(), 10.0)

    def test_total_risk_limit(self):
        self.assertAlmostEqual(self.risk.total_risk_limit(), 10.0)

    def test_reject_boolean_max_positions(self):
        with self.assertRaises(ValueError):
            RiskManager(max_positions=True)

    def test_reject_duplicate_position(self):
        self.assertTrue(
            self.risk.approve_position("trade-1", 5.0)[0]
        )
        self.assertFalse(
            self.risk.approve_position("trade-1", 1.0)[0]
        )

    def test_normalize_position_ids(self):
        self.assertTrue(
            self.risk.approve_position(" trade-1 ", 2.0)[0]
        )
        self.assertFalse(
            self.risk.approve_position("trade-1", 2.0)[0]
        )

    def test_reject_risk_above_per_trade_limit(self):
        approved, _ = self.risk.approve_position("trade-1", 10.01)
        self.assertFalse(approved)

    def test_reject_combined_risk_above_limit(self):
        self.assertTrue(
            self.risk.approve_position("trade-1", 8.0)[0]
        )
        approved, _ = self.risk.approve_position("trade-2", 3.0)
        self.assertFalse(approved)

    def test_reject_more_than_maximum_positions(self):
        for number in range(5):
            approved, _ = self.risk.approve_position(
                f"trade-{number}", 1.0
            )
            self.assertTrue(approved)

        approved, _ = self.risk.approve_position("trade-6", 1.0)
        self.assertFalse(approved)

    def test_invalid_equity_update(self):
        for value in (0, -100, float("nan"), float("inf"), True):
            approved, _ = self.risk.update_equity(value)
            self.assertFalse(approved)

    def test_equity_drop_blocks_additional_risk(self):
        self.assertTrue(
            self.risk.approve_position("trade-1", 8.0)[0]
        )
        self.assertTrue(self.risk.update_equity(50.0)[0])

        approved, _ = self.risk.approve_position("trade-2", 1.0)
        self.assertFalse(approved)

    def test_close_position(self):
        self.assertTrue(
            self.risk.approve_position("trade-1", 5.0)[0]
        )
        self.assertTrue(self.risk.close_position("trade-1")[0])
        self.assertEqual(self.risk.current_risk(), 0.0)


if __name__ == "__main__":
    unittest.main()
