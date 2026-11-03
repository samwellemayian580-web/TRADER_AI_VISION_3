import math


class PositionSizer:
    def __init__(
        self,
        risk_percent=1.0,
        max_risk_percent=10.0,
        min_lot=0.01,
        max_lot=100.0,
        lot_step=0.01
    ):
        self.risk_percent = risk_percent
        self.max_risk_percent = max_risk_percent
        self.min_lot = min_lot
        self.max_lot = max_lot
        self.lot_step = lot_step

    def calculate(
        self,
        equity,
        entry_price,
        stop_loss,
        contract_size,
        account_currency_per_usd=1.0,
        side="BUY"
    ):
        values = [
            equity, entry_price, stop_loss, contract_size,
            account_currency_per_usd, self.risk_percent,
            self.max_risk_percent, self.min_lot,
            self.max_lot, self.lot_step
        ]

        if any(
            not isinstance(v, (int, float))
            or isinstance(v, bool)
            or not math.isfinite(v)
            or v <= 0
            for v in values
        ):
            return {"approved": False, "reason": "Invalid input"}

        if side not in ("BUY", "SELL"):
            return {"approved": False, "reason": "Side must be BUY or SELL"}

        if (
            self.risk_percent > self.max_risk_percent
            or self.max_risk_percent > 100
            or self.max_lot < self.min_lot
            or self.lot_step > self.max_lot
        ):
            return {
                "approved": False,
                "reason": "Invalid risk or lot configuration"
            }

        # Require the minimum lot to align with the broker's lot step.
        min_steps = self.min_lot / self.lot_step
        if not math.isclose(min_steps, round(min_steps), abs_tol=1e-8):
            return {
                "approved": False,
                "reason": "Minimum lot is not aligned with lot step"
            }

        # Verify stop-loss direction.
        if side == "BUY" and stop_loss >= entry_price:
            return {
                "approved": False,
                "reason": "BUY stop-loss must be below entry"
            }

        if side == "SELL" and stop_loss <= entry_price:
            return {
                "approved": False,
                "reason": "SELL stop-loss must be above entry"
            }

        distance = abs(entry_price - stop_loss)

        risk_budget = equity * self.risk_percent / 100
        max_risk_cash = equity * self.max_risk_percent / 100

        # Simplified estimate. Broker tick-value calculations are still needed.
        loss_per_lot = (
            distance * contract_size * account_currency_per_usd
        )

        if not math.isfinite(loss_per_lot) or loss_per_lot <= 0:
            return {
                "approved": False,
                "reason": "Invalid estimated loss per lot"
            }

        raw_lot = risk_budget / loss_per_lot

        if not math.isfinite(raw_lot) or raw_lot <= 0:
            return {
                "approved": False,
                "reason": "Invalid calculated lot"
            }

        if raw_lot < self.min_lot:
            lot = self.min_lot
            minimum_lot_override = True
        else:
            lot = (
                math.floor(raw_lot / self.lot_step + 1e-10)
                * self.lot_step
            )
            minimum_lot_override = False

        # Round down to a valid broker step.
        lot = round(lot, 8)

        if lot > self.max_lot:
            lot = (
                math.floor(self.max_lot / self.lot_step + 1e-10)
                * self.lot_step
            )
            lot = round(lot, 8)

        if lot < self.min_lot:
            return {
                "approved": False,
                "reason": "No valid broker lot available"
            }

        actual_risk = lot * loss_per_lot
        actual_risk_percent = actual_risk / equity * 100

        if actual_risk > max_risk_cash + 1e-9:
            return {
                "approved": False,
                "reason": "Calculated lot exceeds hard risk ceiling",
                "calculated_lot": lot,
                "estimated_risk": round(actual_risk, 4),
                "actual_risk_percent": round(actual_risk_percent, 2),
                "maximum_risk_cash": round(max_risk_cash, 4)
            }

        return {
            "approved": True,
            "side": side,
            "equity": equity,
            "risk_budget": round(risk_budget, 4),
            "maximum_risk_cash": round(max_risk_cash, 4),
            "entry": entry_price,
            "stop_loss": stop_loss,
            "stop_distance": distance,
            "calculated_lot": lot,
            "minimum_lot_override": minimum_lot_override,
            "estimated_risk": round(actual_risk, 4),
            "actual_risk_percent": round(actual_risk_percent, 2),
            "risk_exceeds_target": actual_risk > risk_budget + 1e-9,
            "warning": (
                "Risk exceeds normal target but is within hard ceiling"
                if actual_risk > risk_budget + 1e-9 else None
            )
        }
