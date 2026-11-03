import math

from analysis.market_analyzer import MarketAnalyzer


class HistoricalBacktester:

    def __init__(
        self,
        starting_balance=100.0,
        risk_percent=1.0,
        reward_ratio=2.0,
        atr_stop_multiple=1.5,
        spread=0.0,
        slippage=0.0,
        commission_per_trade=0.0
    ):
        values = [
            starting_balance,
            risk_percent,
            reward_ratio,
            atr_stop_multiple,
            spread,
            slippage,
            commission_per_trade
        ]

        if any(
            not isinstance(v, (int, float))
            or isinstance(v, bool)
            or not math.isfinite(v)
            for v in values
        ):
            raise ValueError("All settings must be finite numbers")

        if starting_balance <= 0:
            raise ValueError("Starting balance must be positive")

        if not 0 < risk_percent <= 10:
            raise ValueError("Risk must be between 0 and 10 percent")

        if reward_ratio <= 0 or atr_stop_multiple <= 0:
            raise ValueError("Invalid stop or reward settings")

        if spread < 0 or slippage < 0 or commission_per_trade < 0:
            raise ValueError("Trading costs cannot be negative")

        self.starting_balance = float(starting_balance)
        self.balance = float(starting_balance)
        self.risk_percent = float(risk_percent)
        self.reward_ratio = float(reward_ratio)
        self.atr_stop_multiple = float(atr_stop_multiple)
        self.spread = float(spread)
        self.slippage = float(slippage)
        self.commission = float(commission_per_trade)

        self.analyzer = MarketAnalyzer()
        self.trades = []
        self.equity_curve = [self.balance]
        self.signals_checked = 0

    def _prepare_candles(self, candles):
        if not isinstance(candles, list):
            raise ValueError("Candles must be a list")

        cleaned = []

        for candle in candles:
            if not isinstance(candle, dict):
                continue

            if candle.get("isOpen") is True:
                continue

            item = dict(candle)

            try:
                for key in ["open", "high", "low", "close"]:
                    item[key] = float(item[key])

                prices = [
                    item["open"], item["high"],
                    item["low"], item["close"]
                ]

                if not all(math.isfinite(x) and x > 0 for x in prices):
                    continue

                if (
                    item["high"] < max(item["open"], item["close"])
                    or item["low"] > min(item["open"], item["close"])
                    or item["high"] < item["low"]
                ):
                    continue

                cleaned.append(item)

            except (KeyError, TypeError, ValueError):
                continue

        if cleaned and all("openTime" in c for c in cleaned):
            cleaned.sort(key=lambda c: c["openTime"])

        if len(cleaned) < 61:
            raise ValueError("At least 61 valid completed candles are required")

        return cleaned

    def _simulate_exit(self, candles, start, direction, stop, target):
        for index in range(start, len(candles)):
            candle = candles[index]

            o = candle["open"]
            h = candle["high"]
            l = candle["low"]

            if direction == "BUY":
                if o <= stop:
                    return index, min(o, stop), "STOP_LOSS"

                if o >= target:
                    return index, target, "TAKE_PROFIT"

                hit_stop = l <= stop
                hit_target = h >= target

            else:
                if o >= stop:
                    return index, max(o, stop), "STOP_LOSS"

                if o <= target:
                    return index, target, "TAKE_PROFIT"

                hit_stop = h >= stop
                hit_target = l <= target

            if hit_stop and hit_target:
                return index, stop, "STOP_LOSS_SAME_CANDLE"

            if hit_stop:
                return index, stop, "STOP_LOSS"

            if hit_target:
                return index, target, "TAKE_PROFIT"

        last = candles[-1]
        return len(candles) - 1, last["close"], "END_OF_DATA"

    def run(self, candles):
        candles = self._prepare_candles(candles)

        self.balance = self.starting_balance
        self.trades = []
        self.equity_curve = [self.balance]
        self.signals_checked = 0

        index = 59

        while index < len(candles) - 1 and self.balance > 0:

            history = candles[:index + 1]
            result = self.analyzer.analyze(history)

            self.signals_checked += 1

            signal = result.get("decision")

            if signal not in ["BUY_SETUP", "SELL_SETUP"]:
                index += 1
                continue

            atr = result.get("atr14")

            if (
                not isinstance(atr, (int, float))
                or not math.isfinite(atr)
                or atr <= 0
            ):
                index += 1
                continue

            direction = "BUY" if signal == "BUY_SETUP" else "SELL"

            entry_candle = candles[index + 1]
            raw_entry = entry_candle["open"]

            half_spread = self.spread / 2

            if direction == "BUY":
                entry = raw_entry + half_spread + self.slippage
            else:
                entry = raw_entry - half_spread - self.slippage

            stop_distance = atr * self.atr_stop_multiple

            if stop_distance <= 0 or entry <= 0:
                index += 1
                continue

            if direction == "BUY":
                stop = entry - stop_distance
                target = entry + stop_distance * self.reward_ratio
            else:
                stop = entry + stop_distance
                target = entry - stop_distance * self.reward_ratio

            risk_cash = self.balance * self.risk_percent / 100

            exit_index, raw_exit, exit_reason = self._simulate_exit(
                candles,
                index + 1,
                direction,
                stop,
                target
            )

            if direction == "BUY":
                exit_price = raw_exit - half_spread - self.slippage
                price_move = exit_price - entry
            else:
                exit_price = raw_exit + half_spread + self.slippage
                price_move = entry - exit_price

            gross_pnl = risk_cash * (price_move / stop_distance)
            net_pnl = gross_pnl - self.commission

            balance_before = self.balance
            self.balance += net_pnl

            self.trades.append({
                "direction": direction,
                "entry_time": entry_candle.get("openTime", index + 1),
                "exit_time": candles[exit_index].get("openTime", exit_index),
                "entry": round(entry, 3),
                "stop_loss": round(stop, 3),
                "take_profit": round(target, 3),
                "exit": round(exit_price, 3),
                "exit_reason": exit_reason,
                "risk_cash": round(risk_cash, 2),
                "gross_pnl": round(gross_pnl, 2),
                "commission": round(self.commission, 2),
                "net_pnl": round(net_pnl, 2),
                "balance_before": round(balance_before, 2),
                "balance_after": round(self.balance, 2)
            })

            self.equity_curve.append(self.balance)

            index = exit_index

        return self.report()

    def report(self):
        wins = [t for t in self.trades if t["net_pnl"] > 0]
        losses = [t for t in self.trades if t["net_pnl"] < 0]

        gross_profit = sum(t["net_pnl"] for t in wins)
        gross_loss = abs(sum(t["net_pnl"] for t in losses))

        peak = self.starting_balance
        max_drawdown = 0.0

        for equity in self.equity_curve:
            peak = max(peak, equity)

            if peak > 0:
                drawdown = (peak - equity) / peak * 100
                max_drawdown = max(max_drawdown, drawdown)

        count = len(self.trades)

        return {
            "starting_balance": round(self.starting_balance, 2),
            "ending_balance": round(self.balance, 2),
            "net_profit": round(self.balance - self.starting_balance, 2),
            "total_trades": count,
            "wins": len(wins),
            "losses": len(losses),
            "win_rate_percent": round(
                len(wins) / count * 100, 2
            ) if count else 0,
            "profit_factor": round(
                gross_profit / gross_loss, 2
            ) if gross_loss else (
                "INFINITY" if gross_profit > 0 else 0
            ),
            "maximum_drawdown_percent": round(max_drawdown, 2),
            "signals_checked": self.signals_checked,
            "execution_authorized": False,
            "cost_warning": (
                "Spread and slippage are zero; results are optimistic"
                if self.spread == 0 and self.slippage == 0
                and self.commission == 0 else None
            )
        }
