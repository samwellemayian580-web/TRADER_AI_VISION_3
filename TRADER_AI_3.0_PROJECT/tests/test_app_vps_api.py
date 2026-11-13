import unittest
from unittest.mock import patch

import app as trader_app
from broker.mt5_bridge_client import BridgeError


class TestVPSAPI(unittest.TestCase):

    def setUp(self):
        self.client = trader_app.app.test_client()
        self.bridge_patch = patch.object(trader_app, "MT5_BRIDGE")
        self.bridge = self.bridge_patch.start()
        self.addCleanup(self.bridge_patch.stop)

    def test_vps_status_success(self):
        self.bridge.check_connection.return_value = {
            "configured": True,
            "connected": True,
            "execution_enabled": False,
            "live_trading": False,
            "message": "Connected"
        }

        response = self.client.get("/vps/status")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["connected"])

    def test_vps_status_disconnected(self):
        self.bridge.check_connection.return_value = {
            "configured": False,
            "connected": False,
            "execution_enabled": False,
            "live_trading": False,
            "message": "Not configured"
        }

        response = self.client.get("/vps/status")

        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.json["connected"])

    def test_vps_account(self):
        self.bridge.get_account.return_value = {
            "balance": 250.0,
            "equity": 247.5,
            "currency": "USD"
        }

        response = self.client.get("/vps/account")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["data"]["balance"], 250.0)

    def test_vps_quote(self):
        self.bridge.get_quote.return_value = {
            "symbol": "XAUUSD",
            "bid": 3950.10,
            "ask": 3950.30
        }

        response = self.client.get("/vps/quote")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["data"]["symbol"], "XAUUSD")

    def test_vps_quote_rejects_other_symbol(self):
        response = self.client.get("/vps/quote?symbol=EURUSD")

        self.assertEqual(response.status_code, 400)
        self.bridge.get_quote.assert_not_called()

    def test_vps_account_handles_bridge_error(self):
        self.bridge.get_account.side_effect = BridgeError(
            "VPS is unavailable"
        )

        response = self.client.get("/vps/account")

        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.json["success"])

    def test_external_access_is_blocked(self):
        response = self.client.get(
            "/vps/account",
            environ_overrides={"REMOTE_ADDR": "192.168.1.20"}
        )

        self.assertEqual(response.status_code, 403)
        self.bridge.get_account.assert_not_called()


if __name__ == "__main__":
    unittest.main()
