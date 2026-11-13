import unittest
from unittest.mock import patch

from broker.mt5_batch_execution import MT5BatchExecutionEngine


class FakeAccount:
    equity = 1000.0
    trade_allowed = True
    trade_mode = 0
    server = "HFM-Demo"


class FakeTerminal:
    connected = True
    trade_allowed = True


class FakeInfo:
    volume_min = 0.01
    volume_max = 100.0
    volume_step = 0.01
    point = 0.01
    trade_stops_level = 0
    trade_mode = 4
    filling_mode = 2


class FakeTick:
    bid = 3950.0
    ask = 3950.2


class FakeResult:
    retcode = 10009
    order = 12345
    deal = 54321
    volume = 0.01
    comment = "Done"


class FakeMT5:
    ACCOUNT_TRADE_MODE_REAL = 2
    ACCOUNT_TRADE_MODE_DEMO = 0
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    ORDER_FILLING_IOC = 1
    SYMBOL_FILLING_IOC = 2
    SYMBOL_TRADE_MODE_DISABLED = 0
    TRADE_ACTION_DEAL = 1
    ORDER_TIME_GTC = 0
    TRADE_RETCODE_DONE = 10009
    TRADE_RETCODE_PLACED = 10008
    TRADE_RETCODE_DONE_PARTIAL = 10010

    def __init__(self):
        self.sent = []
        self.checked = []

    def account_info(self):
        return FakeAccount()

    def terminal_info(self):
        return FakeTerminal()

    def positions_get(self, symbol):
        return []

    def symbol_select(self, symbol, enabled):
        return True

    def symbol_info(self, symbol):
        return FakeInfo()

    def symbol_info_tick(self, symbol):
        return FakeTick()

    def order_calc_profit(self, order_type, symbol, volume, entry, stop):
        return -volume * 100

    def order_check(self, request):
        self.checked.append(dict(request))
        return type("Check", (), {"retcode": 0, "comment": "OK"})()

    def order_send(self, request):
        self.sent.append(dict(request))
        return FakeResult()


class BatchExecutionTests(unittest.TestCase):

    def setUp(self):
        self.mt5 = FakeMT5()
        self.engine = MT5BatchExecutionEngine(self.mt5)
        self.batch = {
            "approved": True,
            "side": "BUY",
            "entry": 3950.2,
            "stop_loss": 3940.0,
            "order_count": 2,
            "orders": [
                {"order_number": 1, "lot": 0.01, "estimated_risk": 1.0},
                {"order_number": 2, "lot": 0.01, "estimated_risk": 1.0},
            ],
            "total_lot": 0.02,
            "total_estimated_risk": 2.0,
        }

    def test_demo_account_is_not_authorized_by_live_only_engine(self):
        with patch.dict("os.environ", {
            "MT5_LIVE_EXECUTION_ENABLED": "YES",
            "MT5_EXPECTED_LIVE_SERVER": "HFM-Live",
        }):
            with self.assertRaises(Exception):
                self.engine.place_batch("setup-1", self.batch, 3970.0)

        self.assertEqual(self.mt5.sent, [])

    def test_rejects_unapproved_batch(self):
        with self.assertRaises(Exception):
            self.engine.place_batch(
                "setup-1", {"approved": False}, 3970.0
            )

        self.assertEqual(self.mt5.sent, [])

    def test_rejects_wrong_child_count(self):
        self.batch["order_count"] = 3

        with patch.dict("os.environ", {
            "MT5_LIVE_EXECUTION_ENABLED": "YES",
            "MT5_EXPECTED_LIVE_SERVER": "HFM-Demo",
        }):
            with self.assertRaises(Exception):
                self.engine.place_batch("setup-1", self.batch, 3970.0)

        self.assertEqual(self.mt5.sent, [])

    def test_rejects_excessive_risk_before_sending(self):
        self.mt5.order_calc_profit = (
            lambda *args: -600.0
        )

        with patch.dict("os.environ", {
            "MT5_LIVE_EXECUTION_ENABLED": "YES",
            "MT5_EXPECTED_LIVE_SERVER": "HFM-Demo",
        }):
            with self.assertRaises(Exception):
                self.engine.place_batch("setup-1", self.batch, 3970.0)

        self.assertEqual(self.mt5.sent, [])


    def test_demo_account_authorizes_in_demo_mode(self):
        with patch.dict("os.environ", {
            "MT5_EXECUTION_MODE": "DEMO",
            "MT5_DEMO_EXECUTION_ENABLED": "YES",
            "MT5_EXPECTED_DEMO_SERVER": "HFM-Demo",
        }, clear=False):
            account = self.engine._authorize()

        self.assertEqual(account.trade_mode, FakeMT5.ACCOUNT_TRADE_MODE_DEMO)
        self.assertEqual(account.server, "HFM-Demo")

    def test_live_account_authorizes_in_live_mode(self):
        live_account = FakeAccount()
        live_account.trade_mode = FakeMT5.ACCOUNT_TRADE_MODE_REAL
        live_account.server = "HFM-Live"

        with patch.object(self.mt5, "account_info", return_value=live_account), \
             patch.dict("os.environ", {
                 "MT5_EXECUTION_MODE": "LIVE",
                 "MT5_LIVE_EXECUTION_ENABLED": "YES",
                 "MT5_EXPECTED_LIVE_SERVER": "HFM-Live",
             }, clear=False):
            account = self.engine._authorize()

        self.assertEqual(account.trade_mode, FakeMT5.ACCOUNT_TRADE_MODE_REAL)
        self.assertEqual(account.server, "HFM-Live")


if __name__ == "__main__":
    unittest.main()
