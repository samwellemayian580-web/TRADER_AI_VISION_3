import unittest
from risk.position_sizer import PositionSizer


class TestPositionSizer(unittest.TestCase):
    def setUp(self):
        self.sizer = PositionSizer()

    def test_calculates_valid_position(self):
        result = self.sizer.calculate(
            equity=1000, entry_price=3000,
            stop_loss=2990, contract_size=100
        )
        self.assertTrue(result["approved"])
        self.assertAlmostEqual(result["calculated_lot"], 0.01)
        self.assertAlmostEqual(result["estimated_risk"], 10.0)

    def test_rejects_invalid_equity(self):
        result = self.sizer.calculate(
            equity=0, entry_price=3000,
            stop_loss=2990, contract_size=100
        )
        self.assertFalse(result["approved"])

    def test_rejects_negative_values(self):
        result = self.sizer.calculate(
            equity=1000, entry_price=3000,
            stop_loss=2990, contract_size=-100
        )
        self.assertFalse(result["approved"])

    def test_rejects_non_finite_values(self):
        result = self.sizer.calculate(
            equity=float("nan"), entry_price=3000,
            stop_loss=2990, contract_size=100
        )
        self.assertFalse(result["approved"])

    def test_rejects_minimum_lot_above_hard_risk_limit(self):
        result = self.sizer.calculate(
            equity=100, entry_price=3000,
            stop_loss=2990, contract_size=1000
        )
        self.assertFalse(result["approved"])

    def test_rejects_invalid_risk_configuration(self):
        sizer = PositionSizer(risk_percent=11, max_risk_percent=10)
        result = sizer.calculate(
            equity=1000, entry_price=3000,
            stop_loss=2990, contract_size=100
        )
        self.assertFalse(result["approved"])

    def test_respects_lot_step(self):
        result = self.sizer.calculate(
            equity=5000, entry_price=3000,
            stop_loss=2990, contract_size=100
        )
        self.assertTrue(result["approved"])
        steps = result["calculated_lot"] / self.sizer.lot_step
        self.assertAlmostEqual(steps, round(steps))

    def test_rejects_buy_stop_above_entry(self):
        result = self.sizer.calculate(
            equity=1000, entry_price=3000,
            stop_loss=3010, contract_size=100, side="BUY"
        )
        self.assertFalse(result["approved"])

    def test_rejects_sell_stop_below_entry(self):
        result = self.sizer.calculate(
            equity=1000, entry_price=3000,
            stop_loss=2990, contract_size=100, side="SELL"
        )
        self.assertFalse(result["approved"])

    def test_accepts_valid_sell_position(self):
        result = self.sizer.calculate(
            equity=1000, entry_price=3000,
            stop_loss=3010, contract_size=100, side="SELL"
        )
        self.assertTrue(result["approved"])
        self.assertEqual(result["side"], "SELL")

    def test_rejects_invalid_side(self):
        result = self.sizer.calculate(
            equity=1000, entry_price=3000,
            stop_loss=2990, contract_size=100, side="HOLD"
        )
        self.assertFalse(result["approved"])

    def test_rejects_minimum_lot_not_aligned_to_step(self):
        sizer = PositionSizer(min_lot=0.015, lot_step=0.01)
        result = sizer.calculate(
            equity=1000, entry_price=3000,
            stop_loss=2990, contract_size=100
        )
        self.assertFalse(result["approved"])


if __name__ == "__main__":
    unittest.main()
