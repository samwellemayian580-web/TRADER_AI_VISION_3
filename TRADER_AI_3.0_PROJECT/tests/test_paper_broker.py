import unittest

from broker.paper_broker import PaperBroker


class TestPaperBroker(unittest.TestCase):

    def setUp(self):
        self.broker = PaperBroker(starting_equity=1000)

    def test_starts_in_paper_mode(self):
        account = self.broker.get_account()
        self.assertEqual(account["mode"], "PAPER")
        self.assertFalse(account["live_trading"])

    def test_opens_buy_position(self):
        result = self.broker.place_order(
            "XAUUSD", "BUY", 0.01, 4000, 3990, 4020
        )
        self.assertTrue(result["success"])
        self.assertEqual(len(self.broker.get_positions()), 1)

    def test_opens_sell_position(self):
        result = self.broker.place_order(
            "XAUUSD", "SELL", 0.01, 4000, 4010, 3980
        )
        self.assertTrue(result["success"])

    def test_closes_position_and_updates_balance(self):
        result = self.broker.place_order(
            "XAUUSD", "BUY", 0.01, 4000, 3990, 4020
        )
        ticket = result["position"]["ticket"]

        closed = self.broker.close_position(ticket, 4010)

        self.assertAlmostEqual(closed["profit"], 0.1)
        self.assertAlmostEqual(self.broker.balance, 1000.1)
        self.assertEqual(len(self.broker.get_positions()), 0)

    def test_rejects_wrong_symbol(self):
        with self.assertRaises(ValueError):
            self.broker.place_order(
                "EURUSD", "BUY", 0.01, 4000, 3990, 4020
            )

    def test_rejects_wrong_buy_stop_direction(self):
        with self.assertRaises(ValueError):
            self.broker.place_order(
                "XAUUSD", "BUY", 0.01, 4000, 4010, 4020
            )

    def test_rejects_wrong_sell_target_direction(self):
        with self.assertRaises(ValueError):
            self.broker.place_order(
                "XAUUSD", "SELL", 0.01, 4000, 4010, 4020
            )

    def test_rejects_boolean_volume(self):
        with self.assertRaises(ValueError):
            self.broker.place_order(
                "XAUUSD", "BUY", True, 4000, 3990, 4020
            )

    def test_rejects_infinite_price(self):
        with self.assertRaises(ValueError):
            self.broker.place_order(
                "XAUUSD", "BUY", 0.01, float("inf"), 3990, 4020
            )

    def test_rejects_unknown_ticket(self):
        with self.assertRaises(ValueError):
            self.broker.close_position("unknown", 4000)

    def test_live_execution_is_disabled(self):
        self.assertFalse(self.broker.LIVE_TRADING)


if __name__ == "__main__":
    unittest.main()
