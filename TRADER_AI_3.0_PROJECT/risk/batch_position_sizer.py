import math


class BatchPositionSizer:
    def __init__(
        self,
        risk_percent=1.0,
        max_risk_percent=10.0,
        min_lot=0.01,
        max_lot=100.0,
        lot_step=0.01,
        max_orders=20,
    ):
        self.risk_percent = risk_percent
        self.max_risk_percent = max_risk_percent
        self.min_lot = min_lot
        self.max_lot = max_lot
        self.lot_step = lot_step
        self.max_orders = max_orders

    @staticmethod
    def _valid_number(value, allow_zero=False):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False

        try:
            if not math.isfinite(value):
                return False
        except (OverflowError, TypeError, ValueError):
            return False

        return value >= 0 if allow_zero else value > 0

    def calculate(
        self,
        equity,
        entry_price,
        stop_loss,
        contract_size,
        account_currency_per_usd=1.0,
        side="BUY",
        order_count=None,
        available_risk=None,
    ):
        values = [
            equity,
            entry_price,
            stop_loss,
            contract_size,
            account_currency_per_usd,
            self.risk_percent,
            self.max_risk_percent,
            self.min_lot,
            self.max_lot,
            self.lot_step,
        ]

        if not all(self._valid_number(v) for v in values):
            return {
                "approved": False,
                "reason": "Invalid numeric input",
            }

        if (
            not isinstance(self.max_orders, int)
            or isinstance(self.max_orders, bool)
            or self.max_orders < 1
        ):
            return {
                "approved": False,
                "reason": "Invalid maximum order count",
            }

        if (
            self.risk_percent > self.max_risk_percent
            or self.max_risk_percent > 10.0
            or self.min_lot > self.max_lot
        ):
            return {
                "approved": False,
                "reason": "Invalid sizing configuration",
            }

        if not math.isclose(
            self.min_lot / self.lot_step,
            round(self.min_lot / self.lot_step),
            abs_tol=1e-8,
        ):
            return {
                "approved": False,
                "reason": "Minimum lot not aligned to step",
            }

        if side not in ("BUY", "SELL"):
            return {
                "approved": False,
                "reason": "Invalid trade direction",
            }

        if order_count is not None:
            if (
                isinstance(order_count, bool)
                or not isinstance(order_count, int)
                or order_count < 1
                or order_count > self.max_orders
            ):
                return {
                    "approved": False,
                    "reason": "Invalid order count",
                }

        if side == "BUY" and stop_loss >= entry_price:
            return {
                "approved": False,
                "reason": "BUY stop must be below entry",
            }

        if side == "SELL" and stop_loss <= entry_price:
            return {
                "approved": False,
                "reason": "SELL stop must be above entry",
            }

        distance = abs(entry_price - stop_loss)

        try:
            loss_per_lot = (
                distance * contract_size * account_currency_per_usd
            )

            normal_budget = equity * self.risk_percent / 100.0
            hard_limit = equity * self.max_risk_percent / 100.0

            max_steps = math.floor(
                self.max_lot / self.lot_step + 1e-10
            )
            minimum_steps = round(self.min_lot / self.lot_step)

        except (OverflowError, ValueError, ZeroDivisionError):
            return {
                "approved": False,
                "reason": "Sizing calculation overflow",
            }

        if (
            not math.isfinite(loss_per_lot)
            or loss_per_lot <= 0
            or not math.isfinite(normal_budget)
            or not math.isfinite(hard_limit)
            or max_steps < minimum_steps
            or minimum_steps < 1
        ):
            return {
                "approved": False,
                "reason": "Invalid calculated sizing values",
            }

        if available_risk is None:
            risk_budget = normal_budget
        else:
            if not self._valid_number(available_risk, allow_zero=True):
                return {
                    "approved": False,
                    "reason": "Invalid available risk",
                }

            risk_budget = min(normal_budget, available_risk)

        risk_budget = min(risk_budget, hard_limit)

        if risk_budget <= 0:
            return {
                "approved": False,
                "reason": "No available risk budget",
            }

        raw_total_lot = risk_budget / loss_per_lot

        try:
            raw_steps = raw_total_lot / self.lot_step
            if not math.isfinite(raw_steps):
                raise OverflowError

            total_steps = math.floor(raw_steps + 1e-10)

            if order_count is None:
                order_capacity = max_steps * self.max_orders
            else:
                order_capacity = max_steps * order_count

            total_steps = min(total_steps, order_capacity)

        except (OverflowError, ValueError):
            return {
                "approved": False,
                "reason": "Lot calculation overflow",
            }

        if total_steps < minimum_steps:
            return {
                "approved": False,
                "reason": "Risk budget cannot afford minimum lot",
            }

        if order_count is not None:
            if total_steps < order_count * minimum_steps:
                return {
                    "approved": False,
                    "reason": "Insufficient risk budget for requested orders",
                }

            count = order_count

        else:
            # Enough orders to respect max_lot, while using
            # as many orders as the available budget supports.
            minimum_count = math.ceil(total_steps / max_steps)
            preferred_count = min(
                self.max_orders,
                total_steps // minimum_steps,
            )
            count = max(minimum_count, preferred_count)

        if (
            count < 1
            or count > self.max_orders
            or total_steps < count * minimum_steps
        ):
            return {
                "approved": False,
                "reason": "Insufficient risk budget for batch",
            }

        base_steps = total_steps // count
        extra_steps = total_steps % count

        orders = []
        total_lot = 0.0
        total_risk_raw = 0.0

        for i in range(count):
            steps = base_steps + (1 if i < extra_steps else 0)
            lot = steps * self.lot_step

            if lot < self.min_lot - 1e-10:
                return {
                    "approved": False,
                    "reason": "Calculated order below minimum lot",
                }

            if lot > self.max_lot + 1e-10:
                return {
                    "approved": False,
                    "reason": "Calculated order exceeds maximum lot",
                }

            order_risk_raw = lot * loss_per_lot

            if not math.isfinite(order_risk_raw):
                return {
                    "approved": False,
                    "reason": "Order risk calculation overflow",
                }

            total_lot += lot
            total_risk_raw += order_risk_raw

            orders.append({
                "order_number": i + 1,
                "lot": round(lot, 8),
                "estimated_risk": round(order_risk_raw, 4),
            })

        tolerance = max(1e-10, risk_budget * 1e-12)

        if (
            not math.isfinite(total_risk_raw)
            or total_risk_raw > risk_budget + tolerance
        ):
            return {
                "approved": False,
                "reason": "Batch exceeds available risk",
            }

        return {
            "approved": True,
            "side": side,
            "equity": equity,
            "entry": entry_price,
            "stop_loss": stop_loss,
            "stop_distance": distance,
            "order_count": len(orders),
            "orders": orders,
            "total_lot": round(total_lot, 8),
            "risk_budget": round(risk_budget, 4),
            "total_estimated_risk": round(total_risk_raw, 4),
            "actual_risk_percent": round(
                total_risk_raw / equity * 100,
                4,
            ),
            "loss_per_lot": round(loss_per_lot, 4),
            "warning": (
                "Broker tick-value, commission and slippage validation required"
            ),
        }
