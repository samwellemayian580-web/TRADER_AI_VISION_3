import math
from bisect import bisect_left

from data.historical_adapter import HistoricalDataAdapter
from analysis.multi_timeframe_analyzer import MultiTimeframeAnalyzer
from risk.risk_manager import RiskManager
from risk.batch_position_sizer import BatchPositionSizer
from risk.batch_execution_manager import BatchExecutionManager


class MultiTimeframeBacktester:
    def __init__(
        self,
        starting_balance=100.0,
        risk_percent=1.0,
        reward_ratio=2.0,
        atr_stop_multiple=1.5,
        spread_price=0.0,
        slippage_price=0.0,
        commission_per_trade=0.0,
        window_size=300,
        contract_size=100.0,
        account_currency_per_usd=1.0,
        batch_max_orders=20,
    ):
        numeric_values = {
            "starting_balance": starting_balance,
            "risk_percent": risk_percent,
            "reward_ratio": reward_ratio,
            "atr_stop_multiple": atr_stop_multiple,
            "spread_price": spread_price,
            "slippage_price": slippage_price,
            "commission_per_trade": commission_per_trade,
            "contract_size": contract_size,
            "account_currency_per_usd": account_currency_per_usd,
        }

        for name, value in numeric_values.items():
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
            ):
                raise ValueError(f"Invalid {name}")

        if starting_balance <= 0:
            raise ValueError("Starting balance must be positive")

        if not 0 < risk_percent <= 10:
            raise ValueError("Risk must be above 0% and at most 10%")

        if reward_ratio <= 0 or atr_stop_multiple <= 0:
            raise ValueError("Reward ratio and ATR multiple must be positive")

        if min(spread_price, slippage_price, commission_per_trade) < 0:
            raise ValueError("Trading costs cannot be negative")

        if contract_size <= 0 or account_currency_per_usd <= 0:
            raise ValueError(
                "Contract size and currency conversion must be positive"
            )

        if (
            not isinstance(window_size, int)
            or isinstance(window_size, bool)
            or window_size < 1
        ):
            raise ValueError("Window size must be a positive integer")

        if (
            not isinstance(batch_max_orders, int)
            or isinstance(batch_max_orders, bool)
            or batch_max_orders < 1
        ):
            raise ValueError("Batch maximum orders must be a positive integer")

        self.starting_balance = float(starting_balance)
        self.balance = float(starting_balance)
        self.risk_percent = float(risk_percent)
        self.reward_ratio = float(reward_ratio)
        self.atr_stop_multiple = float(atr_stop_multiple)
        self.spread_price = float(spread_price)
        self.slippage_price = float(slippage_price)
        self.commission_per_trade = float(commission_per_trade)
        self.window_size = window_size
        self.contract_size = float(contract_size)
        self.account_currency_per_usd = float(account_currency_per_usd)
        self.batch_max_orders = batch_max_orders

        self.adapter = HistoricalDataAdapter()
        self.analyzer = MultiTimeframeAnalyzer()

        self.trades = []
        self.equity_curve = [self.balance]
        self.position = None
        self.pending_signal = None
        self.batch_positions = {}

        self._reset_risk_system()

    def _reset_risk_system(self):
        self.risk_manager = RiskManager(
            equity=self.balance,
            risk_per_trade=self.risk_percent,
            max_risk_per_trade=10.0,
            max_total_risk=10.0,
            max_positions=5,
        )

        self.batch_sizer = BatchPositionSizer(
            risk_percent=self.risk_percent,
            max_risk_percent=10.0,
            max_orders=self.batch_max_orders,
        )

        self.batch_manager = BatchExecutionManager(self.risk_manager)

    def _prepare_snapshot(self, snapshot):
        for timeframe, data in snapshot.items():
            data["candles"] = data["candles"][-self.window_size:]
        return snapshot

    def _entry_cost(self):
        return self.spread_price / 2 + self.slippage_price

    def _exit_fill(self, side, exit_price):
        cost = self._entry_cost()
        if side == "BUY":
            return exit_price - cost
        return exit_price + cost

    # Original single-position entry retained for compatibility.
    def _enter_position(self, candle, signal, index):
        side = signal["side"]
        atr = signal["atr"]
        distance = atr * self.atr_stop_multiple

        if distance <= 0 or self.balance <= 0:
            return False

        updated, message = self.risk_manager.update_equity(self.balance)
        if not updated:
            return False

        risk_cash = self.balance * self.risk_percent / 100.0
        position_id = f"backtest-{index}"

        approved, message = self.risk_manager.approve_position(
            position_id, risk_cash
        )
        if not approved:
            return False

        entry_cost = self._entry_cost()

        if side == "BUY":
            entry = candle["open"] + entry_cost
            stop = entry - distance
            target = entry + distance * self.reward_ratio
        else:
            entry = candle["open"] - entry_cost
            stop = entry + distance
            target = entry - distance * self.reward_ratio

        self.position = {
            "side": side,
            "entry": entry,
            "stop": stop,
            "target": target,
            "distance": distance,
            "risk_cash": risk_cash,
            "risk_id": position_id,
            "entry_index": index,
            "signal_time": signal["signal_time"],
            "analysis": signal.get("analysis", {}),
        }

        return True

    # Original single-position close retained for compatibility.
    def _close_position(self, exit_price, reason, index):
        position = self.position
        exit_cost = self._entry_cost()

        if position["side"] == "BUY":
            fill = exit_price - exit_cost
            movement = fill - position["entry"]
        else:
            fill = exit_price + exit_cost
            movement = position["entry"] - fill

        r_multiple = movement / position["distance"]
        gross_pnl = position["risk_cash"] * r_multiple
        net_pnl = gross_pnl - self.commission_per_trade

        self.balance += net_pnl

        risk_id = position.get("risk_id")
        if risk_id is not None:
            released, message = self.risk_manager.close_position(risk_id)
            if not released:
                raise RuntimeError(
                    f"Failed to release position risk: {message}"
                )

        if self.balance > 0:
            updated, message = self.risk_manager.update_equity(self.balance)
            if not updated:
                raise RuntimeError(
                    f"Failed to update risk manager equity: {message}"
                )

        self.trades.append({
            "side": position["side"],
            "entry": round(position["entry"], 5),
            "exit": round(fill, 5),
            "stop": round(position["stop"], 5),
            "target": round(position["target"], 5),
            "risk_cash": round(position["risk_cash"], 2),
            "gross_pnl": round(gross_pnl, 2),
            "net_pnl": round(net_pnl, 2),
            "r_multiple": round(r_multiple, 3),
            "result": "WIN" if net_pnl > 0 else "LOSS",
            "exit_reason": reason,
            "signal_time": position["signal_time"],
            "exit_index": index,
            "analysis": position.get("analysis", {}),
        })

        self.equity_curve.append(self.balance)
        self.position = None

    def _check_exit(self, candle, index):
        position = self.position

        if position is None:
            return False

        open_price = candle["open"]
        high = candle["high"]
        low = candle["low"]

        if position["side"] == "BUY":
            if open_price <= position["stop"]:
                self._close_position(
                    open_price, "STOP_LOSS_GAP", index
                )
                return True

            stop_hit = low <= position["stop"]
            target_hit = high >= position["target"]

        else:
            if open_price >= position["stop"]:
                self._close_position(
                    open_price, "STOP_LOSS_GAP", index
                )
                return True

            stop_hit = high >= position["stop"]
            target_hit = low <= position["target"]

        # Conservative rule: stop first if both levels are touched.
        if stop_hit:
            self._close_position(
                position["stop"], "STOP_LOSS", index
            )
            return True

        if target_hit:
            self._close_position(
                position["target"], "TAKE_PROFIT", index
            )
            return True

        return False

    # Batch entry: one setup-level reservation, multiple child orders.
    def _enter_batch_position(self, candle, signal, index):
        side = signal["side"]
        atr = signal["atr"]

        if side not in ("BUY", "SELL"):
            return False

        if (
            self.balance <= 0
            or not math.isfinite(atr)
            or atr <= 0
        ):
            return False

        distance = atr * self.atr_stop_multiple
        if not math.isfinite(distance) or distance <= 0:
            return False

        updated, message = self.risk_manager.update_equity(self.balance)
        if not updated:
            return False

        entry_cost = self._entry_cost()

        if side == "BUY":
            entry = candle["open"] + entry_cost
            stop = entry - distance
            target = entry + distance * self.reward_ratio
        else:
            entry = candle["open"] - entry_cost
            stop = entry + distance
            target = entry - distance * self.reward_ratio

        risk_status = self.risk_manager.status()
        available_risk = risk_status["remaining_risk"]

        batch = self.batch_sizer.calculate(
            equity=self.balance,
            entry_price=entry,
            stop_loss=stop,
            contract_size=self.contract_size,
            account_currency_per_usd=self.account_currency_per_usd,
            side=side,
            available_risk=available_risk,
        )

        if not batch.get("approved"):
            return False

        setup_id = f"backtest-batch-{index}"

        created, message = self.batch_manager.create_batch(
            setup_id,
            batch,
            target,
        )

        if not created:
            return False

        self.batch_positions[setup_id] = {
            "setup_id": setup_id,
            "side": side,
            "entry": entry,
            "stop": stop,
            "target": target,
            "distance": distance,
            "entry_index": index,
            "signal_time": signal["signal_time"],
            "analysis": signal.get("analysis", {}),
            "order_count": batch["order_count"],
        }

        return True

    # Close one child order and record its individual result.
    def _close_batch_order(
        self, setup_id, order_id, exit_price, reason, index
    ):
        metadata = self.batch_positions.get(setup_id)
        if metadata is None:
            return False

        setup = self.batch_manager.setups.get(setup_id)
        if setup is None:
            return False

        # IMPORTANT: setup["orders"] is a dictionary.
        order = next(
            (
                item
                for item in setup["orders"].values()
                if item["order_id"] == order_id
            ),
            None,
        )

        if order is None or order["status"] != "OPEN":
            return False

        fill = self._exit_fill(metadata["side"], exit_price)

        if metadata["side"] == "BUY":
            movement = fill - metadata["entry"]
        else:
            movement = metadata["entry"] - fill

        r_multiple = movement / metadata["distance"]
        gross_pnl = order["estimated_risk"] * r_multiple
        net_pnl = gross_pnl - self.commission_per_trade

        # Manager releases setup risk only when the final child closes.
        closed, message = self.batch_manager.close_order(
            setup_id,
            order_id,
            fill,
            reason,
        )

        if not closed:
            raise RuntimeError(
                f"Failed to close batch order: {message}"
            )

        self.balance += net_pnl

        if self.balance > 0:
            updated, message = self.risk_manager.update_equity(self.balance)
            if not updated:
                raise RuntimeError(
                    f"Failed to update risk manager equity: {message}"
                )

        self.trades.append({
            "side": metadata["side"],
            "setup_id": setup_id,
            "order_id": order_id,
            "lot": order["lot"],
            "entry": round(metadata["entry"], 5),
            "exit": round(fill, 5),
            "stop": round(metadata["stop"], 5),
            "target": round(metadata["target"], 5),
            "risk_cash": round(order["estimated_risk"], 4),
            "gross_pnl": round(gross_pnl, 2),
            "net_pnl": round(net_pnl, 2),
            "r_multiple": round(r_multiple, 3),
            "result": "WIN" if net_pnl > 0 else "LOSS",
            "exit_reason": reason,
            "signal_time": metadata["signal_time"],
            "entry_index": metadata["entry_index"],
            "exit_index": index,
            "analysis": metadata.get("analysis", {}),
        })

        self.equity_curve.append(self.balance)

        if setup["status"] == "CLOSED":
            self.batch_positions.pop(setup_id, None)

        return True

    def _close_entire_batch(
        self, setup_id, exit_price, reason, index
    ):
        setup = self.batch_manager.setups.get(setup_id)
        if setup is None:
            return False

        # IMPORTANT: iterate over dictionary values, not dictionary keys.
        open_orders = [
            order["order_id"]
            for order in setup["orders"].values()
            if order["status"] == "OPEN"
        ]

        closed_any = False

        for order_id in open_orders:
            closed = self._close_batch_order(
                setup_id,
                order_id,
                exit_price,
                reason,
                index,
            )
            closed_any = closed_any or closed

        return closed_any

    def _check_batch_exits(self, candle, index):
        closed_this_candle = False

        for setup_id, metadata in list(self.batch_positions.items()):
            open_price = candle["open"]
            high = candle["high"]
            low = candle["low"]

            side = metadata["side"]
            stop = metadata["stop"]
            target = metadata["target"]

            if side == "BUY":
                if open_price <= stop:
                    exit_price = open_price
                    reason = "STOP_LOSS_GAP"
                elif low <= stop:
                    exit_price = stop
                    reason = "STOP_LOSS"
                elif high >= target:
                    exit_price = target
                    reason = "TAKE_PROFIT"
                else:
                    continue

            else:
                if open_price >= stop:
                    exit_price = open_price
                    reason = "STOP_LOSS_GAP"
                elif high >= stop:
                    exit_price = stop
                    reason = "STOP_LOSS"
                elif low <= target:
                    exit_price = target
                    reason = "TAKE_PROFIT"
                else:
                    continue

            closed = self._close_entire_batch(
                setup_id,
                exit_price,
                reason,
                index,
            )

            closed_this_candle = closed_this_candle or closed

        return closed_this_candle

    def _drawdown(self):
        peak = self.starting_balance
        max_drawdown = 0.0

        for equity in self.equity_curve:
            peak = max(peak, equity)

            if peak > 0:
                drawdown = (peak - equity) / peak * 100
                max_drawdown = max(max_drawdown, drawdown)

        return max_drawdown

    def _report(self, strategy, decisions_checked):
        wins = sum(t["net_pnl"] > 0 for t in self.trades)
        losses = sum(t["net_pnl"] <= 0 for t in self.trades)

        gross_profit = sum(
            t["net_pnl"]
            for t in self.trades
            if t["net_pnl"] > 0
        )

        gross_loss = abs(sum(
            t["net_pnl"]
            for t in self.trades
            if t["net_pnl"] < 0
        ))

        total = len(self.trades)

        profit_factor = (
            gross_profit / gross_loss
            if gross_loss > 0
            else None
        )

        batch_setups = len({
            trade["setup_id"]
            for trade in self.trades
            if "setup_id" in trade
        })

        return {
            "strategy": strategy,
            "data_source": "Twelve Data session-filtered XAU/USD proxy",
            "starting_balance": round(self.starting_balance, 2),
            "ending_balance": round(self.balance, 2),
            "net_profit": round(
                self.balance - self.starting_balance, 2
            ),
            "return_percent": round(
                (self.balance / self.starting_balance - 1) * 100, 2
            ),
            "total_trades": total,
            "batch_setups": batch_setups,
            "wins": wins,
            "losses": losses,
            "win_rate_percent": (
                round(wins / total * 100, 2) if total else 0
            ),
            "profit_factor": (
                round(profit_factor, 3)
                if profit_factor is not None
                else None
            ),
            "max_drawdown_percent": round(self._drawdown(), 2),
            "decisions_checked": decisions_checked,
            "risk_percent": self.risk_percent,
            "batch_max_orders": self.batch_max_orders,
            "contract_size_assumption": self.contract_size,
            "account_currency_per_usd_assumption": (
                self.account_currency_per_usd
            ),
            "execution_authorized": False,
            "pnl_model": (
                "Normalized R-based estimate using estimated batch risk; "
                "not verified HFM cash PnL"
            ),
            "warning": (
                "Contract size and currency conversion are configurable "
                "backtesting assumptions, not verified HFM specifications. "
                "Spread, slippage, commission, tick value and live execution "
                "must be validated before any real-money trading."
            ),
        }

    def run(self, strategy="SCALPING", max_decisions=500):
        strategy = strategy.upper()

        if strategy not in ("SCALPING", "SWING"):
            raise ValueError("Strategy must be SCALPING or SWING")

        # Reset all run-specific state before every backtest.
        self.balance = self.starting_balance
        self.trades = []
        self.equity_curve = [self.starting_balance]
        self.position = None
        self.pending_signal = None
        self.batch_positions = {}
        self._reset_risk_system()

        times = self.adapter.get_decision_times()

        required_times = [
            self.adapter.close_times[tf][59]
            for tf in ("M5", "M15", "H1", "H4")
            if len(self.adapter.close_times[tf]) >= 60
        ]

        if len(required_times) != 4:
            raise ValueError("Not enough historical candles")

        earliest_valid_time = max(required_times)
        start_index = bisect_left(times, earliest_valid_time)

        if start_index >= len(times):
            raise ValueError("No valid historical decision times")

        available = len(times) - start_index

        limit = (
            available
            if max_decisions is None
            else min(available, int(max_decisions))
        )

        if limit <= 0:
            raise ValueError("No decisions available")

        decisions_checked = 0

        for index in range(start_index, start_index + limit):
            decision_time = times[index]
            candle = self.adapter.data["M5"][index]

            # A pending signal enters at the next M5 candle open.
            if (
                self.pending_signal is not None
                and self.position is None
            ):
                self._enter_batch_position(
                    candle,
                    self.pending_signal,
                    index,
                )
                self.pending_signal = None

            # Check exits for legacy single positions and batch setups.
            legacy_closed = self._check_exit(candle, index)
            batch_closed = self._check_batch_exits(candle, index)

            if (
                self.position is not None
                or legacy_closed
                or batch_closed
            ):
                continue

            if index == len(times) - 1:
                continue

            snapshot = self.adapter.get_snapshot(
                decision_time,
                max_candles=self.window_size,
            )

            result = self.analyzer.analyze(
                snapshot,
                strategy=strategy,
            )

            decisions_checked += 1

            decision = result.get("decision")
            timeframe_results = result.get("timeframe_results", {})
            m5_result = timeframe_results.get("M5", {})

            diagnostic_fields = (
                "decision",
                "reason",
                "trend",
                "close",
                "ema20",
                "ema50",
                "rsi14",
                "atr14",
                "patterns",
                "candles_analyzed",
            )

            analysis_snapshot = {
                "strategy": strategy,
                "decision": decision,
                "reason": result.get("reason"),
                "timeframe_trends": result.get(
                    "timeframe_trends", {}
                ),
                "timeframes": {
                    tf: {
                        field: timeframe_results.get(tf, {}).get(field)
                        for field in diagnostic_fields
                    }
                    for tf in ("M5", "M15", "H1", "H4")
                },
            }

            atr = m5_result.get("atr14")

            if decision == "BUY_SETUP" and atr:
                self.pending_signal = {
                    "side": "BUY",
                    "atr": float(atr),
                    "signal_time": decision_time.isoformat(),
                    "analysis": analysis_snapshot,
                }

            elif decision == "SELL_SETUP" and atr:
                self.pending_signal = {
                    "side": "SELL",
                    "atr": float(atr),
                    "signal_time": decision_time.isoformat(),
                    "analysis": analysis_snapshot,
                }

        # Close any remaining legacy position at the final available close.
        final_index = start_index + limit - 1
        last_candle = self.adapter.data["M5"][final_index]

        if self.position is not None:
            self._close_position(
                last_candle["close"],
                "END_OF_TEST",
                final_index,
            )

        # Close every remaining batch child individually.
        for setup_id in list(self.batch_positions):
            self._close_entire_batch(
                setup_id,
                last_candle["close"],
                "END_OF_TEST",
                final_index,
            )

        self.pending_signal = None

        return self._report(strategy, decisions_checked)
