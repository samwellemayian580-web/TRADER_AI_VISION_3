import math


class RiskManager:
    def __init__(
        self,
        equity=10.0,
        risk_per_trade=1.0,
        max_risk_per_trade=10.0,
        max_total_risk=10.0,
        max_positions=5
    ):
        self.equity = equity
        self.risk_per_trade = risk_per_trade
        self.max_risk_per_trade = max_risk_per_trade
        self.max_total_risk = max_total_risk
        self.max_positions = max_positions
        self.positions = {}

        values = [equity, risk_per_trade, max_risk_per_trade, max_total_risk]

        if any(
            not isinstance(v, (int, float))
            or isinstance(v, bool)
            or not math.isfinite(v)
            or v <= 0
            for v in values
        ):
            raise ValueError("Invalid risk configuration")

        if risk_per_trade > max_risk_per_trade:
            raise ValueError("Normal risk exceeds maximum risk")

        if max_risk_per_trade > max_total_risk or max_total_risk > 100:
            raise ValueError("Invalid maximum risk limits")

        if (
            not isinstance(max_positions, int)
            or isinstance(max_positions, bool)
            or max_positions < 1
        ):
            raise ValueError("Invalid maximum positions")

    def update_equity(self, new_equity):
        if (
            not isinstance(new_equity, (int, float))
            or isinstance(new_equity, bool)
            or not math.isfinite(new_equity)
            or new_equity <= 0
        ):
            return False, "Invalid account equity"

        self.equity = float(new_equity)
        return True, "Account equity updated"

    def risk_amount(self):
        return self.equity * self.risk_per_trade / 100

    def max_trade_risk(self):
        return self.equity * self.max_risk_per_trade / 100

    def total_risk_limit(self):
        return self.equity * self.max_total_risk / 100

    def current_risk(self):
        return sum(self.positions.values())

    def approve_position(self, position_id, risk_cash):
        if not isinstance(position_id, str) or not position_id.strip():
            return False, "Invalid position ID"

        position_id = position_id.strip()

        if (
            not isinstance(risk_cash, (int, float))
            or isinstance(risk_cash, bool)
            or not math.isfinite(risk_cash)
            or risk_cash <= 0
        ):
            return False, "Invalid risk amount"

        if position_id in self.positions:
            return False, "Position already registered"

        if len(self.positions) >= self.max_positions:
            return False, "Maximum open positions reached"

        if risk_cash > self.max_trade_risk() + 1e-9:
            return False, "10% per-trade risk ceiling exceeded"

        if self.current_risk() + risk_cash > self.total_risk_limit() + 1e-9:
            return False, "Combined 10% risk limit exceeded"

        self.positions[position_id] = float(risk_cash)
        return True, "Position approved"

    def close_position(self, position_id):
        if not isinstance(position_id, str) or not position_id.strip():
            return False, "Invalid position ID"

        position_id = position_id.strip()

        if position_id not in self.positions:
            return False, "Position not found"

        del self.positions[position_id]
        return True, "Position removed"

    def status(self):
        current = self.current_risk()

        return {
            "equity": round(self.equity, 2),
            "normal_target_percent": self.risk_per_trade,
            "max_risk_per_trade_percent": self.max_risk_per_trade,
            "max_total_risk_percent": self.max_total_risk,
            "max_positions": self.max_positions,
            "open_positions": len(self.positions),
            "current_open_risk": round(current, 4),
            "remaining_risk": round(
                max(0, self.total_risk_limit() - current), 4
            )
        }
