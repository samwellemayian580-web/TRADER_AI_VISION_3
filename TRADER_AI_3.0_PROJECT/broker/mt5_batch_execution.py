import os
"""Preflight validation and controlled batch execution for TRADER AI VISION 3.0."""

import math
from broker.mt5_execution import ExecutionError, MT5ExecutionEngine


class MT5BatchExecutionEngine(MT5ExecutionEngine):
    """Validate all child orders before sending any order."""

    def _authorize(self):
        mode = os.getenv("MT5_EXECUTION_MODE", "LIVE").strip().upper()

        if mode not in ("DEMO", "LIVE"):
            raise ExecutionError("Execution mode must be DEMO or LIVE")

        account = self.mt5.account_info()
        terminal = self.mt5.terminal_info()

        if account is None or terminal is None:
            raise ExecutionError("MT5 account or terminal information unavailable")

        if not getattr(terminal, "connected", False):
            raise ExecutionError("MT5 terminal is not connected")

        if not getattr(account, "trade_allowed", False):
            raise ExecutionError("Trading is not allowed on this account")

        if not getattr(terminal, "trade_allowed", False):
            raise ExecutionError("Trading is disabled in the MT5 terminal")

        if not math.isfinite(float(getattr(account, "equity", 0) or 0)) or account.equity <= 0:
            raise ExecutionError("Account equity is invalid")

        if mode == "DEMO":
            enabled = os.getenv("MT5_DEMO_EXECUTION_ENABLED", "").upper() == "YES"
            expected_server = os.getenv("MT5_EXPECTED_DEMO_SERVER", "").strip()
            expected_type = getattr(self.mt5, "ACCOUNT_TRADE_MODE_DEMO", 0)
        else:
            enabled = os.getenv("MT5_LIVE_EXECUTION_ENABLED", "").upper() == "YES"
            expected_server = os.getenv("MT5_EXPECTED_LIVE_SERVER", "").strip()
            expected_type = getattr(self.mt5, "ACCOUNT_TRADE_MODE_REAL", 2)

        if not enabled:
            raise ExecutionError(f"{mode} execution is disabled")

        if not expected_server:
            raise ExecutionError(f"Expected {mode} server is not configured")

        if getattr(account, "trade_mode", None) != expected_type:
            raise ExecutionError(f"Connected MT5 account is not a {mode} account")

        actual_server = str(getattr(account, "server", "") or "").strip()
        if actual_server != expected_server:
            raise ExecutionError(f"MT5 server mismatch for {mode} account")

        return account

    def _preflight(self, side, volume, stop_loss, take_profit):
        mt5 = self.mt5
        symbol = "XAUUSD"

        volume = self._number(volume, "volume")
        stop_loss = self._number(stop_loss, "stop loss")
        take_profit = self._number(take_profit, "take profit")

        if volume <= 0:
            raise ExecutionError("Volume must be positive.")

        if not mt5.symbol_select(symbol, True):
            raise ExecutionError("Could not select XAUUSD.")

        info = mt5.symbol_info(symbol)
        tick = mt5.symbol_info_tick(symbol)

        if info is None or tick is None:
            raise ExecutionError("XAUUSD market data unavailable.")

        if info.trade_mode == mt5.SYMBOL_TRADE_MODE_DISABLED:
            raise ExecutionError("XAUUSD trading is disabled.")

        self._validate_volume(volume, info)

        point = self._number(info.point, "point size")
        if point <= 0:
            raise ExecutionError("Invalid broker point size.")

        is_buy = side == "BUY"
        price = self._number(tick.ask if is_buy else tick.bid, "market price")

        if is_buy and not stop_loss < price < take_profit:
            raise ExecutionError("BUY requires SL below price and TP above price.")

        if not is_buy and not take_profit < price < stop_loss:
            raise ExecutionError("SELL requires TP below price and SL above price.")

        minimum_distance = (
            self._number(info.trade_stops_level, "stops level") * point
        )

        if abs(price - stop_loss) < minimum_distance:
            raise ExecutionError("Stop loss violates broker minimum distance.")

        if abs(price - take_profit) < minimum_distance:
            raise ExecutionError("Take profit violates broker minimum distance.")

        order_type = mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL
        calculated = mt5.order_calc_profit(
            order_type, symbol, volume, price, stop_loss
        )

        if calculated is None:
            raise ExecutionError("MT5 could not calculate child-order risk.")

        risk = max(
            0.0,
            -self._number(calculated, "child-order risk")
        )

        return {
            "volume": volume,
            "price": price,
            "risk": risk,
            "info": info,
            "order_type": order_type,
        }

    def place_batch(self, setup_id, batch, take_profit):
        if not isinstance(setup_id, str) or not setup_id.strip():
            raise ExecutionError("A valid setup_id is required.")
        if not isinstance(batch, dict) or batch.get("approved") is not True:
            raise ExecutionError("Batch has not been approved by the risk manager.")

        side = batch.get("side")
        if side not in ("BUY", "SELL"):
            raise ExecutionError("Batch side must be BUY or SELL.")
        if batch.get("symbol", "XAUUSD") != "XAUUSD":
            raise ExecutionError("Only XAUUSD is enabled.")

        stop_loss = self._number(batch.get("stop_loss"), "stop loss")
        take_profit = self._number(take_profit, "take profit")
        orders = batch.get("orders")

        if not isinstance(orders, list) or not orders:
            raise ExecutionError("Batch must contain child orders.")
        if batch.get("order_count") != len(orders):
            raise ExecutionError("Batch order count does not match child orders.")

        account = self._authorize()
        equity = self._number(account.equity, "account equity")
        hard_limit = equity * 0.10
        initial_existing_risk = self._position_risk("XAUUSD")

        # Validate every child before sending the first order.
        prepared = []
        total_risk = 0.0
        total_volume = 0.0

        for child in orders:
            if not isinstance(child, dict):
                raise ExecutionError("Invalid child order.")

            item = self._preflight(
                side, child.get("lot"), stop_loss, take_profit
            )
            prepared.append(item)
            total_risk += item["risk"]
            total_volume += item["volume"]

        declared_risk = self._number(
            batch.get("total_estimated_risk"), "declared batch risk"
        )
        declared_volume = self._number(
            batch.get("total_lot"), "declared batch volume"
        )

        if declared_risk <= 0:
            raise ExecutionError("Declared batch risk must be positive.")
        if not math.isclose(
            total_volume, declared_volume, rel_tol=1e-7, abs_tol=1e-8
        ):
            raise ExecutionError("Child volumes do not match declared batch volume.")
        if total_risk > hard_limit:
            raise ExecutionError("Batch exceeds the 10% hard risk ceiling.")
        if initial_existing_risk + total_risk > hard_limit + 1e-8:
            raise ExecutionError("Batch exceeds combined account risk limit.")
        if total_risk > declared_risk * 1.05:
            raise ExecutionError(
                "Broker-calculated risk exceeds the batch estimate by over 5%."
            )

        mt5 = self.mt5
        accepted_codes = {
            getattr(mt5, "TRADE_RETCODE_DONE", 10009),
            getattr(mt5, "TRADE_RETCODE_PLACED", 10008),
            getattr(mt5, "TRADE_RETCODE_DONE_PARTIAL", 10010),
        }

        results = []
        committed_risk = 0.0

        for index, original in enumerate(prepared, start=1):
            try:
                # Refresh account authorization, quote and risk before each child.
                account = self._authorize()
                current_equity = self._number(
                    account.equity, "account equity"
                )
                current_limit = current_equity * 0.10

                item = self._preflight(
                    side,
                    original["volume"],
                    stop_loss,
                    take_profit,
                )

                current_existing = self._position_risk("XAUUSD")
                conservative_existing = max(
                    current_existing,
                    initial_existing_risk + committed_risk,
                )

                if conservative_existing + item["risk"] > current_limit + 1e-8:
                    raise ExecutionError(
                        "Fresh quote would exceed the combined 10% risk limit."
                    )

                info = item["info"]
                flags = int(info.filling_mode)

                if flags & getattr(mt5, "SYMBOL_FILLING_IOC", 2):
                    filling = mt5.ORDER_FILLING_IOC
                elif flags & getattr(mt5, "SYMBOL_FILLING_FOK", 1):
                    filling = mt5.ORDER_FILLING_FOK
                else:
                    raise ExecutionError(
                        "No supported IOC or FOK filling mode found."
                    )

                # Build a new request for this child; never reuse an old request.
                safe_id = "".join(
                    c for c in setup_id if c.isalnum() or c in "-_"
                )[:15] or "setup"

                request = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": "XAUUSD",
                    "volume": item["volume"],
                    "type": item["order_type"],
                    "price": item["price"],
                    "sl": stop_loss,
                    "tp": take_profit,
                    "deviation": 20,
                    "magic": 303000,
                    "comment": f"TAI3:{safe_id}:{index:03d}",
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": filling,
                }

                check = mt5.order_check(request)
                if check is None or check.retcode != 0:
                    raise ExecutionError(
                        f"Child {index} failed MT5 order check: "
                        f"{getattr(check, 'comment', 'No response')}"
                    )

                # Re-authorize immediately before sending.
                self._authorize()
                result = mt5.order_send(request)

                if result is None or result.retcode not in accepted_codes:
                    return {
                        "success": False,
                        "state": "PARTIAL" if results else "UNKNOWN",
                        "setup_id": setup_id,
                        "completed_children": results,
                        "failed_child": index,
                        "reconciliation_required": True,
                        "message": "Order outcome requires MT5 reconciliation.",
                    }

                filled_volume = float(
                    getattr(result, "volume", item["volume"])
                )
                child_result = {
                    "child": index,
                    "ticket": int(getattr(result, "order", 0)),
                    "deal": int(getattr(result, "deal", 0)),
                    "requested_volume": item["volume"],
                    "filled_volume": filled_volume,
                    "risk_cash_estimate": round(item["risk"], 2),
                }
                results.append(child_result)
                committed_risk += item["risk"]

                if result.retcode == getattr(
                    mt5, "TRADE_RETCODE_DONE_PARTIAL", 10010
                ):
                    return {
                        "success": False,
                        "state": "PARTIAL",
                        "setup_id": setup_id,
                        "completed_children": results,
                        "failed_child": index,
                        "reconciliation_required": True,
                        "message": "Partial fill; remaining children were not sent.",
                    }

            except Exception as exc:
                if results:
                    return {
                        "success": False,
                        "state": "PARTIAL",
                        "setup_id": setup_id,
                        "completed_children": results,
                        "failed_child": index,
                        "error": str(exc),
                        "reconciliation_required": True,
                    }
                if isinstance(exc, ExecutionError):
                    raise
                return {
                    "success": False,
                    "state": "UNKNOWN",
                    "setup_id": setup_id,
                    "failed_child": index,
                    "error": str(exc),
                    "reconciliation_required": True,
                }

        return {
            "success": True,
            "state": "SUBMITTED",
            "setup_id": setup_id,
            "symbol": "XAUUSD",
            "side": side,
            "child_count": len(results),
            "total_volume": round(total_volume, 8),
            "broker_calculated_risk": round(total_risk, 2),
            "existing_position_risk": round(initial_existing_risk, 2),
            "equity": round(equity, 2),
            "children": results,
            "message": "Batch submitted. Reconcile final MT5 fills and positions.",
        }
