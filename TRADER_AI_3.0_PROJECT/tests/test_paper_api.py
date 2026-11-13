import unittest

import app as trader_app
from broker.paper_broker import PaperBroker


class TestPaperAPI(unittest.TestCase):

    def setUp(self):
        trader_app.PAPER_BROKER = PaperBroker(starting_equity=1000)
        self.client = trader_app.app.test_client()

    def test_status_endpoint(self):
        response = self.client.get("/paper/status")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["account"]["mode"], "PAPER")

    def test_positions_endpoint(self):
        response = self.client.get("/paper/positions")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["positions"], [])

    def test_open_and_close_simulated_trade(self):
        response = self.client.post("/paper/order", json={
            "symbol": "XAUUSD",
            "side": "BUY",
            "volume": 0.01,
            "entry_price": 4000,
            "stop_loss": 3990,
            "take_profit": 4020
        })
        self.assertEqual(response.status_code, 201)

        ticket = response.get_json()["position"]["ticket"]

        response = self.client.post("/paper/close", json={
            "ticket": ticket,
            "exit_price": 4010
        })
        self.assertEqual(response.status_code, 200)
        self.assertAlmostEqual(response.get_json()["profit"], 0.1)

    def test_invalid_order_is_rejected(self):
        response = self.client.post("/paper/order", json={
            "symbol": "EURUSD",
            "side": "BUY",
            "volume": 0.01,
            "entry_price": 4000,
            "stop_loss": 3990,
            "take_profit": 4020
        })
        self.assertEqual(response.status_code, 400)

    def test_external_access_is_blocked(self):
        response = self.client.get(
            "/paper/status",
            environ_overrides={"REMOTE_ADDR": "192.168.1.10"}
        )
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
