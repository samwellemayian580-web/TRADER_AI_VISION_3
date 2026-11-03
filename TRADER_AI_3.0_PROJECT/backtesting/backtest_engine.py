class BacktestEngine:

    def __init__(
        self,
        starting_balance=100.0,
        risk_percent=1.0,
        reward_ratio=2.0
    ):
        if starting_balance <= 0:
            raise ValueError("Starting balance must be positive")

        if not 0 < risk_percent <= 10:
            raise ValueError("Risk must be above 0 and at most 10%")

        if reward_ratio <= 0:
            raise ValueError("Reward ratio must be positive")

        self.starting_balance = float(starting_balance)
        self.balance = float(starting_balance)
        self.risk_percent = float(risk_percent)
        self.reward_ratio = float(reward_ratio)
        self.trades = []
        self.equity_curve = [self.balance]

    def record_trade(self, entry, stop_loss, outcome):
        if outcome not in ["WIN", "LOSS"]:
            return False, "Outcome must be WIN or LOSS"

        if entry <= 0 or stop_loss <= 0 or entry == stop_loss:
            return False, "Invalid entry or stop loss"

        risk_cash = self.balance * self.risk_percent / 100

        if risk_cash > self.balance * 0.10:
            return False, "Risk ceiling exceeded"

        if outcome == "WIN":
            profit = risk_cash * self.reward_ratio
        else:
            profit = -risk_cash

        self.balance += profit

        self.trades.append({
            "entry": float(entry),
            "stop_loss": float(stop_loss),
            "outcome": outcome,
            "risk_cash": round(risk_cash, 2),
            "profit": round(profit, 2),
            "balance": round(self.balance, 2)
        })

        self.equity_curve.append(self.balance)

        return True, "Trade recorded"

    def report(self):
        wins = sum(
            1 for trade in self.trades
            if trade["outcome"] == "WIN"
        )

        losses = sum(
            1 for trade in self.trades
            if trade["outcome"] == "LOSS"
        )

        total_profit = sum(
            trade["profit"] for trade in self.trades
        )

        gross_profit = sum(
            trade["profit"] for trade in self.trades
            if trade["profit"] > 0
        )

        gross_loss = abs(sum(
            trade["profit"] for trade in self.trades
            if trade["profit"] < 0
        ))

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
            "net_profit": round(total_profit, 2),
            "total_trades": count,
            "wins": wins,
            "losses": losses,
            "win_rate_percent": round(
                wins / count * 100, 2
            ) if count else 0,
            "profit_factor": round(
                gross_profit / gross_loss, 2
            ) if gross_loss else (
                "INFINITY" if gross_profit else 0
            ),
            "maximum_drawdown_percent": round(
                max_drawdown, 2
            )
        }
