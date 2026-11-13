"""Read-only HFM MT5 position reconciliation and contract validation."""

import math


class ReconciliationError(RuntimeError):
    pass


def _positive(value, field):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ReconciliationError(
            "Invalid broker value: " + field
        )
    return float(value)


def _setup_id(position):
    comment = str(getattr(position, "comment", "") or "")
    parts = comment.split(":")

    # Bot child-order comments use TAI:<setup_id>:<child_id>.
    if len(parts) >= 3 and parts[0] == "TAI" and parts[1]:
        return "BOT:" + parts[1]

    # Unknown/manual trades count separately.
    return "MANUAL:" + str(position.ticket)


def get_symbol_specifications(mt5, symbol="XAUUSD"):
    info = mt5.symbol_info(symbol)
    tick = mt5.symbol_info_tick(symbol)

    if info is None or tick is None:
        raise ReconciliationError(
            "Broker did not return symbol specifications or a quote"
        )

    specs = {
        "symbol": symbol,
        "digits": int(info.digits),
        "point": _positive(info.point, "point"),
        "tick_size": _positive(
            info.trade_tick_size, "trade_tick_size"
        ),
        "tick_value": _positive(
            info.trade_tick_value, "trade_tick_value"
        ),
        "tick_value_loss": _positive(
            getattr(
                info,
                "trade_tick_value_loss",
                info.trade_tick_value,
            ),
            "trade_tick_value_loss",
        ),
        "contract_size": _positive(
            info.trade_contract_size, "trade_contract_size"
        ),
        "volume_min": _positive(info.volume_min, "volume_min"),
        "volume_max": _positive(info.volume_max, "volume_max"),
        "volume_step": _positive(info.volume_step, "volume_step"),
        "stops_level_points": int(info.trade_stops_level),
        "freeze_level_points": int(info.trade_freeze_level),
        "trade_mode": int(info.trade_mode),
        "filling_mode": int(info.filling_mode),
        "currency_base": str(info.currency_base),
        "currency_profit": str(info.currency_profit),
        "currency_margin": str(info.currency_margin),
        "bid": _positive(tick.bid, "bid"),
        "ask": _positive(tick.ask, "ask"),
        "quote_time": int(tick.time),
    }

    if specs["volume_min"] > specs["volume_max"]:
        raise ReconciliationError("Invalid broker volume range")

    if specs["ask"] < specs["bid"]:
        raise ReconciliationError("Invalid bid/ask spread")

    return specs


def reconcile_positions(mt5, symbol="XAUUSD"):
    """Calculate stop-loss exposure for every open XAUUSD position.

    Any position without a verifiable stop loss makes the snapshot
    incomplete. Callers must block new execution in that situation.
    """

    account = mt5.account_info()
    if account is None:
        raise ReconciliationError("MT5 account information unavailable")

    equity = _positive(account.equity, "account equity")

    positions = mt5.positions_get(symbol=symbol)
    if positions is None:
        raise ReconciliationError(
            "MT5 could not retrieve open positions: "
            + str(mt5.last_error())
        )

    groups = {}
    details = []
    unverified = []

    for position in positions:
        setup_id = _setup_id(position)
        side = (
            "BUY"
            if position.type == mt5.POSITION_TYPE_BUY
            else "SELL"
            if position.type == mt5.POSITION_TYPE_SELL
            else None
        )

        if side is None:
            unverified.append({
                "ticket": int(position.ticket),
                "reason": "Unknown position direction",
            })
            continue

        stop = float(position.sl or 0)
        entry = _positive(position.price_open, "position entry")
        volume = _positive(position.volume, "position volume")

        if stop <= 0:
            unverified.append({
                "ticket": int(position.ticket),
                "reason": "Position has no stop loss",
            })
            continue

        if side == "BUY" and stop >= entry:
            unverified.append({
                "ticket": int(position.ticket),
                "reason": "BUY stop loss is not below entry",
            })
            continue

        if side == "SELL" and stop <= entry:
            unverified.append({
                "ticket": int(position.ticket),
                "reason": "SELL stop loss is not above entry",
            })
            continue

        order_type = (
            mt5.ORDER_TYPE_BUY
            if side == "BUY"
            else mt5.ORDER_TYPE_SELL
        )

        loss_at_stop = mt5.order_calc_profit(
            order_type,
            symbol,
            volume,
            entry,
            stop,
        )

        if (
            loss_at_stop is None
            or isinstance(loss_at_stop, bool)
            or not isinstance(loss_at_stop, (int, float))
            or not math.isfinite(loss_at_stop)
        ):
            unverified.append({
                "ticket": int(position.ticket),
                "reason": "Broker could not calculate loss at stop",
            })
            continue

        if loss_at_stop > 0.01:
            unverified.append({
                "ticket": int(position.ticket),
                "reason": "Stop calculation unexpectedly shows a profit",
            })
            continue

        risk_cash = abs(min(0.0, float(loss_at_stop)))

        group = groups.setdefault(setup_id, {
            "setup_id": setup_id,
            "child_positions": 0,
            "risk_cash": 0.0,
            "tickets": [],
        })

        group["child_positions"] += 1
        group["risk_cash"] += risk_cash
        group["tickets"].append(int(position.ticket))

        details.append({
            "ticket": int(position.ticket),
            "setup_id": setup_id,
            "side": side,
            "volume": volume,
            "entry": entry,
            "stop_loss": stop,
            "risk_cash": round(risk_cash, 4),
        })

    total_risk = sum(
        group["risk_cash"] for group in groups.values()
    )

    risk_percent = total_risk / equity * 100

    complete = len(unverified) == 0

    return {
        "account_currency": str(account.currency),
        "equity": round(equity, 2),
        "symbol": symbol,
        "risk_complete": complete,
        "new_execution_allowed": False,
        "open_setups": len(groups),
        "open_child_positions": len(details),
        "combined_stop_loss_risk": round(total_risk, 4),
        "combined_risk_percent": round(risk_percent, 4),
        "setups": list(groups.values()),
        "positions": details,
        "unverified_positions": unverified,
        "risk_calculation": "MT5 order_calc_profit at stop loss",
        "limitations": [
            "Commission and future slippage are not included",
            "Positions without stop losses block new execution",
            "Only XAUUSD positions are included",
            "Pending orders are not included",
            "This module does not place or close trades",
        ],
    }
