import unittest
from risk.batch_position_sizer import BatchPositionSizer


class TestBatchPositionSizer(unittest.TestCase):

    def test_splits_risk_into_multiple_orders(self):
        sizer = BatchPositionSizer()

        result = sizer.calculate(
            equity=500,
            entry_price=3000,
            stop_loss=2999,
            contract_size=100,
        )

        self.assertTrue(result["approved"])
        self.assertEqual(result["order_count"], 5)
        self.assertAlmostEqual(result["total_lot"], 0.05)
        self.assertAlmostEqual(result["total_estimated_risk"], 5.0)

        for order in result["orders"]:
            self.assertAlmostEqual(order["lot"], 0.01)

    def test_max_lot_applies_to_each_order(self):
        sizer = BatchPositionSizer(max_lot=0.02)

        result = sizer.calculate(
            equity=500,
            entry_price=3000,
            stop_loss=2999,
            contract_size=100,
            order_count=3,
        )

        self.assertTrue(result["approved"])
        self.assertEqual(result["order_count"], 3)
        self.assertAlmostEqual(result["total_lot"], 0.05)

        for order in result["orders"]:
            self.assertLessEqual(order["lot"], 0.02)

    def test_respects_available_risk(self):
        sizer = BatchPositionSizer()

        result = sizer.calculate(
            equity=500,
            entry_price=3000,
            stop_loss=2999,
            contract_size=100,
            available_risk=2,
        )

        self.assertTrue(result["approved"])
        self.assertLessEqual(result["total_estimated_risk"], 2.0)

    def test_rejects_invalid_order_count(self):
        sizer = BatchPositionSizer()

        result = sizer.calculate(
            equity=500,
            entry_price=3000,
            stop_loss=2999,
            contract_size=100,
            order_count=0,
        )

        self.assertFalse(result["approved"])



    def test_sell_batch_sizing(self):
        sizer = BatchPositionSizer()
        result = sizer.calculate(
            equity=500,
            entry_price=3000,
            stop_loss=3001,
            contract_size=100,
            side="SELL",
        )
        self.assertTrue(result["approved"])
        self.assertEqual(result["order_count"], 5)
        self.assertAlmostEqual(result["total_estimated_risk"], 5.0)

    def test_uneven_batch_respects_per_order_maximum(self):
        sizer = BatchPositionSizer(max_lot=0.02)
        result = sizer.calculate(
            equity=500,
            entry_price=3000,
            stop_loss=2999,
            contract_size=100,
            order_count=3,
        )
        self.assertTrue(result["approved"])
        self.assertEqual(
            [order["lot"] for order in result["orders"]],
            [0.02, 0.02, 0.01],
        )

    def test_rejects_wrong_sell_stop_direction(self):
        sizer = BatchPositionSizer()
        result = sizer.calculate(
            equity=500,
            entry_price=3000,
            stop_loss=2999,
            contract_size=100,
            side="SELL",
        )
        self.assertFalse(result["approved"])

    def test_rejects_risk_limit_above_ten_percent(self):
        sizer = BatchPositionSizer(
            risk_percent=1,
            max_risk_percent=11,
        )
        result = sizer.calculate(
            equity=500,
            entry_price=3000,
            stop_loss=2999,
            contract_size=100,
        )
        self.assertFalse(result["approved"])

    def test_rejects_invalid_trade_direction(self):
        sizer = BatchPositionSizer()
        result = sizer.calculate(
            equity=500,
            entry_price=3000,
            stop_loss=2999,
            contract_size=100,
            side="HOLD",
        )
        self.assertFalse(result["approved"])


    def test_rejects_invalid_max_orders_type(self):
        sizer = BatchPositionSizer(max_orders="20")
        result = sizer.calculate(
            equity=500,
            entry_price=3000,
            stop_loss=2999,
            contract_size=100,
        )
        self.assertFalse(result["approved"])

    def test_rejects_zero_available_risk(self):
        sizer = BatchPositionSizer()
        result = sizer.calculate(
            equity=500,
            entry_price=3000,
            stop_loss=2999,
            contract_size=100,
            available_risk=0,
        )
        self.assertFalse(result["approved"])

    def test_rejects_unaligned_minimum_lot(self):
        sizer = BatchPositionSizer(
            min_lot=0.015,
            lot_step=0.01,
        )
        result = sizer.calculate(
            equity=500,
            entry_price=3000,
            stop_loss=2999,
            contract_size=100,
        )
        self.assertFalse(result["approved"])

    def test_rejects_order_count_above_limit(self):
        sizer = BatchPositionSizer(max_orders=5)
        result = sizer.calculate(
            equity=500,
            entry_price=3000,
            stop_loss=2999,
            contract_size=100,
            order_count=6,
        )
        self.assertFalse(result["approved"])

    def test_ten_percent_hard_risk_boundary(self):
        sizer = BatchPositionSizer(
            risk_percent=10,
            max_risk_percent=10,
        )
        result = sizer.calculate(
            equity=500,
            entry_price=3000,
            stop_loss=2999,
            contract_size=100,
        )
        self.assertTrue(result["approved"])
        self.assertLessEqual(result["actual_risk_percent"], 10.0)
        self.assertAlmostEqual(result["total_estimated_risk"], 50.0)

    def test_automatic_batch_respects_small_per_order_maximum(self):
        sizer = BatchPositionSizer(max_lot=0.02)
        result = sizer.calculate(
            equity=500,
            entry_price=3000,
            stop_loss=2999,
            contract_size=100,
        )
        self.assertTrue(result["approved"])
        self.assertAlmostEqual(result["total_lot"], 0.05)
        for order in result["orders"]:
            self.assertLessEqual(order["lot"], 0.02)


if __name__ == "__main__":
    unittest.main()
