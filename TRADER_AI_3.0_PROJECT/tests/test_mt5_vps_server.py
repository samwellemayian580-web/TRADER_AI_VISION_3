import unittest
from types import SimpleNamespace

from broker.mt5_vps_server import create_app


TOKEN = "test-secret"


class FakeTerminalInfo:
    connected = True
    trade_allowed = True


class FakeAccountInfo:
    balance = 250.0
    equity = 247.5
    currency = "USD"
    leverage = 500
    server = "HFM-Demo"
    trade_allowed = True


class FakeSymbolInfo:
    digits = 2
    point = 0.01
    trade_contract_size = 100.0
    volume_min = 0.01
    volume_max = 100.0
    volume_step = 0.01
    volume_limit = 100.0
    trade_tick_size = 0.01
    trade_tick_value = 1.0
    trade_tick_value_profit = 1.0
    trade_tick_value_loss = 1.0
    trade_stops_level = 0
    trade_freeze_level = 0
    trade_mode = 4
    currency_base = "XAU"
    currency_profit = "USD"
    currency_margin = "USD"
    filling_mode = 1


class FakeTick:
    bid = 3950.10
    ask = 3950.30
    time = 1790000000


class FakeMT5:
    POSITION_TYPE_BUY = 0
    POSITION_TYPE_SELL = 1
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1

    def __init__(self):
        self.positions = []
    def positions_get(self, symbol=None):
        return self.positions

    def order_calc_profit(self, order_type, symbol, volume, entry, stop):
        return -100.0 * volume

    def initialize(self):
        return True

    def last_error(self):
        return (0, "OK")

    def terminal_info(self):
        return FakeTerminalInfo()

    def account_info(self):
        return FakeAccountInfo()

    def symbol_info(self, symbol):
        return FakeSymbolInfo() if symbol == "XAUUSD" else None

    def symbol_info_tick(self, symbol):
        return FakeTick() if symbol == "XAUUSD" else None




def make_position(ticket, comment="", side=0, entry=3950.0,
                  stop=3940.0, volume=0.01):
    return SimpleNamespace(
        ticket=ticket,
        symbol="XAUUSD",
        comment=comment,
        type=side,
        price_open=entry,
        sl=stop,
        volume=volume,
    )


class MT5VPSServerTests(unittest.TestCase):

    def setUp(self):
        self.mt5 = FakeMT5()
        self.app = create_app(token=TOKEN, mt5_module=self.mt5)
        self.client = self.app.test_client()
        self.headers = {"Authorization": f"Bearer {TOKEN}"}

    def test_health_requires_authentication(self):
        response = self.client.get("/api/v1/health")
        self.assertEqual(response.status_code, 401)

    def test_health_with_token(self):
        response = self.client.get(
            "/api/v1/health", headers=self.headers
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["data"] if "data" in response.json else response.json["mode"], "READ_ONLY")

    def test_status_returns_demo_server(self):
        response = self.client.get(
            "/api/v1/mt5/status", headers=self.headers
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["data"]["server"], "HFM-Demo")
        self.assertFalse(response.json["data"]["live_execution_enabled"])

    def test_account_returns_balance_and_equity(self):
        response = self.client.get(
            "/api/v1/mt5/account", headers=self.headers
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["data"]["balance"], 250.0)
        self.assertEqual(response.json["data"]["equity"], 247.5)

    def test_xauusd_quote_returns_broker_specs(self):
        response = self.client.get(
            "/api/v1/mt5/quote/XAUUSD", headers=self.headers
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["data"]["bid"], 3950.10)
        data = response.json["data"]
        self.assertEqual(data["volume_min"], 0.01)
        self.assertEqual(data["tick_size"], 0.01)
        self.assertEqual(data["tick_value"], 1.0)
        self.assertEqual(data["tick_value_profit"], 1.0)
        self.assertEqual(data["tick_value_loss"], 1.0)
        self.assertEqual(data["stops_level"], 0)
        self.assertEqual(data["freeze_level"], 0)
        self.assertEqual(data["currency_profit"], "USD")

    def test_other_symbols_are_rejected(self):
        response = self.client.get(
            "/api/v1/mt5/quote/EURUSD", headers=self.headers
        )
        self.assertEqual(response.status_code, 400)

    def test_order_endpoint_is_locked_by_default(self):
        response = self.client.post(
            "/api/v1/mt5/order",
            headers=self.headers,
            json={
                "request_id": "locked-test-001",
                "symbol": "XAUUSD",
                "side": "BUY",
                "volume": 0.01,
                "stop_loss": 3900.0,
                "take_profit": 4000.0,
            },
        )
        self.assertEqual(response.status_code, 423)
        self.assertFalse(response.get_json()["success"])


    def test_reconciliation_requires_authentication(self):
        response = self.client.get("/api/v1/mt5/reconciliation")
        self.assertEqual(response.status_code, 401)

    def test_reconciliation_returns_specs_and_stays_read_only(self):
        response = self.client.get(
            "/api/v1/mt5/reconciliation", headers=self.headers
        )
        self.assertEqual(response.status_code, 200)
        data = response.json["data"]
        self.assertEqual(data["symbol_specifications"]["symbol"], "XAUUSD")
        self.assertEqual(data["symbol_specifications"]["volume_min"], 0.01)
        self.assertEqual(data["symbol_specifications"]["bid"], 3950.10)
        self.assertFalse(data["new_execution_allowed"])
        self.assertFalse(data["reconciliation"]["new_execution_allowed"])

    def test_reconciliation_groups_TAI3_child_orders_and_combines_risk(self):
        self.mt5.positions = [
            make_position(101, "TAI3:setup1:001", volume=0.01),
            make_position(102, "TAI3:setup1:002", volume=0.02),
        ]
        response = self.client.get(
            "/api/v1/mt5/reconciliation", headers=self.headers
        )
        self.assertEqual(response.status_code, 200)
        snapshot = response.json["data"]["reconciliation"]
        self.assertEqual(snapshot["open_setups"], 1)
        self.assertEqual(snapshot["open_child_positions"], 2)
        self.assertAlmostEqual(snapshot["combined_stop_loss_risk"], 3.0)
        self.assertTrue(snapshot["risk_complete"])
        self.assertFalse(snapshot["new_execution_allowed"])

    def test_reconciliation_counts_manual_positions_separately(self):
        self.mt5.positions = [
            make_position(101),
            make_position(102),
        ]
        response = self.client.get(
            "/api/v1/mt5/reconciliation", headers=self.headers
        )
        self.assertEqual(response.status_code, 200)
        snapshot = response.json["data"]["reconciliation"]
        self.assertEqual(snapshot["open_setups"], 2)

    def test_reconciliation_blocks_new_execution_without_stop_loss(self):
        self.mt5.positions = [make_position(101, stop=0)]
        response = self.client.get(
            "/api/v1/mt5/reconciliation", headers=self.headers
        )
        self.assertEqual(response.status_code, 200)
        snapshot = response.json["data"]["reconciliation"]
        self.assertFalse(snapshot["risk_complete"])
        self.assertEqual(len(snapshot["unverified_positions"]), 1)
        self.assertFalse(snapshot["new_execution_allowed"])

    def test_reconciliation_fails_closed_when_positions_unavailable(self):
        self.mt5.positions_get = lambda symbol=None: None
        response = self.client.get(
            "/api/v1/mt5/reconciliation", headers=self.headers
        )
        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.json["new_execution_allowed"])



if __name__ == "__main__":
    unittest.main()
