import unittest
from types import SimpleNamespace

from deployment.windows_vps.broker_reconciliation import (
    ReconciliationError,
    get_symbol_specifications,
    reconcile_positions,
)


class FakeMT5:
    POSITION_TYPE_BUY = 0
    POSITION_TYPE_SELL = 1
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1

    def __init__(self, positions=None):
        self.positions = positions or []

    def symbol_info(self, symbol):
        return SimpleNamespace(
            digits=2,
            point=0.01,
            trade_tick_size=0.01,
            trade_tick_value=1.0,
            trade_tick_value_loss=1.0,
            trade_contract_size=100.0,
            volume_min=0.01,
            volume_max=100.0,
            volume_step=0.01,
            trade_stops_level=0,
            trade_freeze_level=0,
            trade_mode=4,
            filling_mode=1,
            currency_base="XAU",
            currency_profit="USD",
            currency_margin="USD",
        )

    def symbol_info_tick(self, symbol):
        return SimpleNamespace(
            bid=4000.00,
            ask=4000.20,
            time=1800000000,
        )

    def account_info(self):
        return SimpleNamespace(equity=1000.0, currency="USD")

    def positions_get(self, symbol):
        return self.positions

    def order_calc_profit(
        self, order_type, symbol, volume, entry, stop
    ):
        return -100.0 * volume

    def last_error(self):
        return (0, "No error")


def make_position(
    ticket,
    comment="",
    side=FakeMT5.POSITION_TYPE_BUY,
    entry=4000.0,
    stop=3990.0,
    volume=0.01,
):
    return SimpleNamespace(
        ticket=ticket,
        comment=comment,
        type=side,
        price_open=entry,
        sl=stop,
        volume=volume,
    )


class TestBrokerReconciliation(unittest.TestCase):

    def test_reads_valid_symbol_specifications(self):
        specs = get_symbol_specifications(FakeMT5())

        self.assertEqual(specs["symbol"], "XAUUSD")
        self.assertEqual(specs["volume_min"], 0.01)
        self.assertEqual(specs["volume_step"], 0.01)
        self.assertEqual(specs["bid"], 4000.00)
        self.assertEqual(specs["ask"], 4000.20)

    def test_rejects_missing_symbol_information(self):
        mt5 = FakeMT5()
        mt5.symbol_info = lambda symbol: None

        with self.assertRaises(ReconciliationError):
            get_symbol_specifications(mt5)

    def test_groups_child_orders_into_one_setup(self):
        positions = [
            make_position(101, "TAI:setup1:child1"),
            make_position(102, "TAI:setup1:child2"),
        ]
        result = reconcile_positions(FakeMT5(positions))

        self.assertEqual(result["open_setups"], 1)
        self.assertEqual(result["open_child_positions"], 2)
        self.assertEqual(result["setups"][0]["child_positions"], 2)
        self.assertTrue(result["risk_complete"])
        self.assertFalse(result["new_execution_allowed"])

    def test_manual_positions_count_separately(self):
        positions = [make_position(101), make_position(102)]
        result = reconcile_positions(FakeMT5(positions))

        self.assertEqual(result["open_setups"], 2)

    def test_combines_risk_across_all_positions(self):
        positions = [
            make_position(101, "TAI:setup1:child1", volume=0.01),
            make_position(102, "TAI:setup1:child2", volume=0.02),
        ]
        result = reconcile_positions(FakeMT5(positions))

        self.assertAlmostEqual(result["combined_stop_loss_risk"], 3.0)
        self.assertAlmostEqual(result["combined_risk_percent"], 0.3)

    def test_position_without_stop_loss_is_unverified(self):
        result = reconcile_positions(
            FakeMT5([make_position(101, stop=0)])
        )

        self.assertFalse(result["risk_complete"])
        self.assertEqual(len(result["unverified_positions"]), 1)
        self.assertFalse(result["new_execution_allowed"])

    def test_rejects_invalid_buy_stop(self):
        position = make_position(
            101, side=FakeMT5.POSITION_TYPE_BUY,
            entry=4000.0, stop=4010.0,
        )
        result = reconcile_positions(FakeMT5([position]))

        self.assertFalse(result["risk_complete"])

    def test_rejects_invalid_sell_stop(self):
        position = make_position(
            101, side=FakeMT5.POSITION_TYPE_SELL,
            entry=4000.0, stop=3990.0,
        )
        result = reconcile_positions(FakeMT5([position]))

        self.assertFalse(result["risk_complete"])

    def test_empty_account_has_zero_open_risk(self):
        result = reconcile_positions(FakeMT5())

        self.assertTrue(result["risk_complete"])
        self.assertEqual(result["open_setups"], 0)
        self.assertEqual(result["combined_stop_loss_risk"], 0)

    def test_account_information_is_required(self):
        mt5 = FakeMT5()
        mt5.account_info = lambda: None

        with self.assertRaises(ReconciliationError):
            reconcile_positions(mt5)


if __name__ == "__main__":
    unittest.main()
