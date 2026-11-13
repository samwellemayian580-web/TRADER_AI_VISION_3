import unittest

from broker.mt5_bridge_client import MT5BridgeClient


class TestMT5BridgeClient(unittest.TestCase):

    def test_unconfigured_bridge_is_disconnected(self):
        client = MT5BridgeClient(base_url="", token="")
        status = client.get_status()

        self.assertFalse(status["connected"])
        self.assertFalse(status["execution_enabled"])
        self.assertFalse(status["live_trading"])

    def test_https_configuration_is_accepted(self):
        client = MT5BridgeClient(
            base_url="https://example.com",
            token="test-token"
        )

        self.assertTrue(
            client.configuration_status()["configured"]
        )

    def test_http_configuration_is_rejected(self):
        client = MT5BridgeClient(
            base_url="http://example.com",
            token="test-token"
        )

        self.assertFalse(
            client.configuration_status()["configured"]
        )

    def test_missing_token_is_rejected(self):
        client = MT5BridgeClient(
            base_url="https://example.com",
            token=""
        )

        self.assertFalse(
            client.configuration_status()["configured"]
        )

    def test_execution_is_disabled_by_default(self):
        client = MT5BridgeClient(
            base_url="https://example.com",
            token="test-token"
        )

        self.assertFalse(client.execution_enabled)
        self.assertFalse(client.get_status()["live_trading"])


if __name__ == "__main__":
    unittest.main()


class FakeResponse:

    def __init__(self, payload):
        import json
        self.raw = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.raw


class FakeOpener:

    def __init__(self):
        self.calls = []

    def open(self, request, timeout=10):
        self.calls.append(request)

        from urllib.parse import urlparse
        path = urlparse(request.full_url).path

        responses = {
            "/api/v1/health": {
                "success": True,
                "mode": "READ_ONLY"
            },
            "/api/v1/mt5/status": {
                "success": True,
                "data": {
                    "terminal_connected": True,
                    "server": "HFM-Demo",
                    "live_execution_enabled": False
                }
            },
            "/api/v1/mt5/account": {
                "success": True,
                "data": {
                    "balance": 250.0,
                    "equity": 247.5,
                    "currency": "USD"
                }
            },
            "/api/v1/mt5/quote/XAUUSD": {
                "success": True,
                "data": {
                    "symbol": "XAUUSD",
                    "bid": 3950.10,
                    "ask": 3950.30,
                    "volume_min": 0.01
                }
            }
        }

        if path not in responses:
            raise AssertionError("Unexpected endpoint: " + path)

        return FakeResponse(responses[path])


class TestMT5BridgeRequests(unittest.TestCase):

    def setUp(self):
        from broker.mt5_bridge_client import MT5BridgeClient
        self.opener = FakeOpener()
        self.client = MT5BridgeClient(
            base_url="https://example.com",
            token="test-secret",
            opener=self.opener
        )

    def test_health_request(self):
        result = self.client.get_health()
        self.assertTrue(result["success"])

    def test_status_request(self):
        result = self.client.get_mt5_status()
        self.assertEqual(result["server"], "HFM-Demo")
        self.assertTrue(self.client.connected)

    def test_account_request(self):
        result = self.client.get_account()
        self.assertEqual(result["balance"], 250.0)
        self.assertEqual(result["equity"], 247.5)

    def test_xauusd_quote_request(self):
        result = self.client.get_quote()
        self.assertEqual(result["bid"], 3950.10)
        self.assertEqual(result["ask"], 3950.30)

    def test_other_symbol_is_rejected(self):
        from broker.mt5_bridge_client import BridgeError
        with self.assertRaises(BridgeError):
            self.client.get_quote("EURUSD")

    def test_bearer_token_is_sent(self):
        self.client.get_health()
        self.assertEqual(
            self.opener.calls[0].get_header("Authorization"),
            "Bearer test-secret"
        )

    def test_execution_remains_disabled(self):
        self.assertFalse(self.client.execution_enabled)

    def test_connection_check(self):
        result = self.client.check_connection()
        self.assertTrue(result["connected"])
        self.assertFalse(result["live_trading"])
        self.assertFalse(result["execution_enabled"])
