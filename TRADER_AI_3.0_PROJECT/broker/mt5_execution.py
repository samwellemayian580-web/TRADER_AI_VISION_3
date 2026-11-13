
"""Controlled MT5 execution for TRADER AI VISION 3.0."""

import math
import os


class ExecutionError(RuntimeError):
    pass


class MT5ExecutionEngine:
    def __init__(self, mt5_module):
        self.mt5 = mt5_module

    @staticmethod
    def _number(value, name):
        if isinstance(value, bool):
            raise ExecutionError(f"Invalid {name}.")
        try:
            value = float(value)
        except (TypeError, ValueError):
            raise ExecutionError(f"Invalid {name}.")
        if not math.isfinite(value):
            raise ExecutionError(f"Invalid {name}.")
        return value

    def _authorize(self):
        mt5 = self.mt5

        if os.getenv("MT5_LIVE_EXECUTION_ENABLED") != "YES":
            raise ExecutionError("Live execution is disabled.")

        expected_server = os.getenv("MT5_EXPECTED_LIVE_SERVER", "").strip()
        if not expected_server:
            raise ExecutionError("Expected HFM LIVE server is not configured.")

        account = mt5.account_info()
        terminal = mt5.terminal_info()

        if account is None or terminal is None:
            raise ExecutionError("MT5 account or terminal unavailable.")

        real_mode = getattr(mt5, "ACCOUNT_TRADE_MODE_REAL", 2)

        if getattr(account, "trade_mode", None) != real_mode:
            raise ExecutionError("Connected account is not a REAL account.")

        actual_server = str(getattr(account, "server", "")).strip()
        if actual_server != expected_server:
            raise ExecutionError("Connected account is not on the configured HFM LIVE server.")

        if not getattr(account, "trade_allowed", False):
            raise ExecutionError("Account trading permission is disabled.")

        if not getattr(terminal, "trade_allowed", False):
            raise ExecutionError("Terminal trading permission is disabled.")

        if not getattr(terminal, "connected", False):
            raise ExecutionError("MT5 terminal is disconnected.")

        equity = self._number(account.equity, "account equity")
        if equity <= 0:
            raise ExecutionError("Account equity must be positive.")

        return account

    def _position_risk(self, symbol):
        """Calculate risk to stop loss for every existing position on the symbol."""
        mt5 = self.mt5
        positions = mt5.positions_get(symbol=symbol)

        if positions is None:
            raise ExecutionError("Could not retrieve existing MT5 positions.")

        total = 0.0

        for position in positions:
            stop = self._number(position.sl, "existing position stop loss")
            if stop <= 0:
                raise ExecutionError(
                    "An existing XAUUSD position has no stop loss. "
                    "New trading is blocked until its risk is controlled."
                )

            position_type = position.type
            entry = self._number(position.price_open, "existing position entry")
            volume = self._number(position.volume, "existing position volume")

            result = mt5.order_calc_profit(
                position_type, symbol, volume, entry, stop
            )

            if result is None:
                raise ExecutionError("MT5 could not calculate existing position risk.")

            loss = self._number(result, "existing position risk")
            total += max(0.0, -loss)

        return total

    def _validate_volume(self, volume, info):
        minimum = self._number(info.volume_min, "broker minimum volume")
        maximum = self._number(info.volume_max, "broker maximum volume")
        step = self._number(info.volume_step, "broker volume step")

        if step <= 0 or volume < minimum or volume > maximum:
            raise ExecutionError("Volume violates HFM broker limits.")

        steps = volume / step
        if abs(steps - round(steps)) > 1e-7:
            raise ExecutionError("Volume does not match the broker's lot step.")

    def place_market_order(
        self,
        symbol,
        side,
        volume,
        stop_loss,
        take_profit,
    ):
        mt5 = self.mt5

        if symbol != "XAUUSD":
            raise ExecutionError("Only XAUUSD is enabled.")

        if side not in ("BUY", "SELL"):
            raise ExecutionError("Side must be BUY or SELL.")

        volume = self._number(volume, "volume")
        stop_loss = self._number(stop_loss, "stop loss")
        take_profit = self._number(take_profit, "take profit")

        if volume <= 0:
            raise ExecutionError("Volume must be positive.")

        account = self._authorize()

        if not mt5.symbol_select(symbol, True):
            raise ExecutionError("Could not select XAUUSD.")

        info = mt5.symbol_info(symbol)
        tick = mt5.symbol_info_tick(symbol)

        if info is None or tick is None:
            raise ExecutionError("XAUUSD market data unavailable.")

        if info.trade_mode == mt5.SYMBOL_TRADE_MODE_DISABLED:
            raise ExecutionError("XAUUSD trading is disabled.")

        self._validate_volume(volume, info)

        tick_size = self._number(info.trade_tick_size, "tick size")
        point = self._number(info.point, "point size")

        if tick_size <= 0 or point <= 0:
            raise ExecutionError("Invalid broker price specifications.")

        is_buy = side == "BUY"
        price = self._number(tick.ask if is_buy else tick.bid, "market price")

        if is_buy and not stop_loss < price < take_profit:
            raise ExecutionError("BUY requires SL below price and TP above price.")

        if not is_buy and not take_profit < price < stop_loss:
            raise ExecutionError("SELL requires TP below price and SL above price.")

        minimum_distance = self._number(info.trade_stops_level, "stops level") * point

        if abs(price - stop_loss) < minimum_distance:
            raise ExecutionError("Stop loss violates broker minimum distance.")

        if abs(price - take_profit) < minimum_distance:
            raise ExecutionError("Take profit violates broker minimum distance.")

        # Calculate the new order's loss using MT5's account-currency calculator.
        order_type = mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL

        calculated_loss = mt5.order_calc_profit(
            order_type, symbol, volume, price, stop_loss
        )

        if calculated_loss is None:
            raise ExecutionError("MT5 could not calculate the order's stop-loss risk.")

        new_risk = max(
            0.0,
            -self._number(calculated_loss, "calculated order risk")
        )

        equity = self._number(account.equity, "account equity")
        hard_limit = equity * 0.10
        normal_target = equity * 0.01

        if new_risk > hard_limit:
            raise ExecutionError("Order exceeds the 10% hard risk ceiling.")

        existing_risk = self._position_risk(symbol)

        if existing_risk + new_risk > hard_limit + 1e-8:
            raise ExecutionError(
                "Order would exceed the combined 10% account risk ceiling."
            )

        # Select a filling mode supported by the broker symbol.
        filling_flags = int(info.filling_mode)
        if filling_flags & getattr(mt5, "SYMBOL_FILLING_IOC", 2):
            filling = mt5.ORDER_FILLING_IOC
        elif filling_flags & getattr(mt5, "SYMBOL_FILLING_FOK", 1):
            filling = mt5.ORDER_FILLING_FOK
        else:
            raise ExecutionError("No supported IOC or FOK filling mode found.")

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": order_type,
            "price": price,
            "sl": stop_loss,
            "tp": take_profit,
            "deviation": 20,
            "magic": 303000,
            "comment": "TRADER_AI_VISION_3",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling,
        }

        check = mt5.order_check(request)
        if check is None or check.retcode != 0:
            raise ExecutionError(
                "MT5 order check rejected: "
                + str(getattr(check, "comment", "No response"))
            )

        # Recheck account identity and authorization immediately before sending.
        self._authorize()

        result = mt5.order_send(request)

        if result is None:
            raise ExecutionError("MT5 returned no order result.")

        accepted_codes = {
            getattr(mt5, "TRADE_RETCODE_DONE", 10009),
            getattr(mt5, "TRADE_RETCODE_PLACED", 10008),
            getattr(mt5, "TRADE_RETCODE_DONE_PARTIAL", 10010),
        }

        if result.retcode not in accepted_codes:
            raise ExecutionError(
                f"MT5 rejected order: {result.retcode} "
                f"{getattr(result, 'comment', '')}"
            )

        actual_volume = getattr(result, "volume", volume)

        return {
            "success": True,
            "ticket": int(getattr(result, "order", 0)),
            "deal": int(getattr(result, "deal", 0)),
            "requested_volume": volume,
            "filled_volume": float(actual_volume),
            "risk_cash_estimate": round(new_risk, 2),
            "existing_position_risk": round(existing_risk, 2),
            "equity": round(equity, 2),
            "normal_1_percent_target": round(normal_target, 2),
            "above_normal_target": new_risk > normal_target,
            "side": side,
            "symbol": symbol,
            "message": "MT5 accepted the order. Confirm its final fill and position.",
        }
