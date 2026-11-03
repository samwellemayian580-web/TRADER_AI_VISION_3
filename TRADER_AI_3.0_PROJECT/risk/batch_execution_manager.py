import math


class BatchExecutionManager:
    def __init__(self, risk_manager):
        self.risk_manager = risk_manager
        self.setups = {}

    @staticmethod
    def _valid_number(value):
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
            and value > 0
        )

    @staticmethod
    def _valid_id(value):
        return isinstance(value, str) and bool(value.strip())

    def create_batch(self, setup_id, batch, target_price):
        if not self._valid_id(setup_id):
            return False, "Invalid setup ID"

        setup_id = setup_id.strip()

        if setup_id in self.setups:
            return False, "Setup ID already exists"

        if not isinstance(batch, dict) or batch.get("approved") is not True:
            return False, "Batch is not approved"

        side = batch.get("side")
        if side not in ("BUY", "SELL"):
            return False, "Invalid trade direction"

        entry = batch.get("entry")
        stop = batch.get("stop_loss")

        if not self._valid_number(entry) or not self._valid_number(stop):
            return False, "Invalid entry or stop-loss"

        if not self._valid_number(target_price):
            return False, "Invalid target price"

        if side == "BUY":
            if stop >= entry or target_price <= entry:
                return False, "Invalid BUY stop or target direction"
        else:
            if stop <= entry or target_price >= entry:
                return False, "Invalid SELL stop or target direction"

        source_orders = batch.get("orders")
        if not isinstance(source_orders, list) or not source_orders:
            return False, "Batch contains no orders"

        order_count = batch.get("order_count")
        if (
            not isinstance(order_count, int)
            or isinstance(order_count, bool)
            or order_count != len(source_orders)
        ):
            return False, "Order count mismatch"

        orders = {}
        total_risk = 0.0
        total_lot = 0.0

        for index, source in enumerate(source_orders, start=1):
            if not isinstance(source, dict):
                return False, "Invalid order data"

            lot = source.get("lot")
            risk = source.get("estimated_risk")

            if not self._valid_number(lot) or not self._valid_number(risk):
                return False, "Invalid order lot or risk"

            total_risk += risk
            total_lot += lot

            if not math.isfinite(total_risk) or not math.isfinite(total_lot):
                return False, "Batch totals are not finite"

            order_id = f"{setup_id}-O{index:03d}"

            orders[order_id] = {
                "order_id": order_id,
                "order_number": index,
                "lot": float(lot),
                "estimated_risk": float(risk),
                "status": "OPEN",
                "exit_price": None,
                "exit_reason": None,
            }

        declared_risk = batch.get("total_estimated_risk")
        declared_lot = batch.get("total_lot")

        if not self._valid_number(declared_risk):
            return False, "Invalid declared batch risk"

        if not self._valid_number(declared_lot):
            return False, "Invalid declared batch lot"

        if not math.isclose(
            total_risk, declared_risk, rel_tol=1e-8, abs_tol=1e-8
        ):
            return False, "Batch risk total mismatch"

        if not math.isclose(
            total_lot, declared_lot, rel_tol=1e-8, abs_tol=1e-8
        ):
            return False, "Batch lot total mismatch"

        approved, message = self.risk_manager.approve_position(
            setup_id, total_risk
        )

        if not approved:
            return False, message

        self.setups[setup_id] = {
            "setup_id": setup_id,
            "side": side,
            "entry": float(entry),
            "stop_loss": float(stop),
            "target_price": float(target_price),
            "total_lot": float(total_lot),
            "reserved_risk": float(total_risk),
            "status": "OPEN",
            "orders": orders,
        }

        return True, "Batch created successfully"

    def close_order(self, setup_id, order_id, exit_price, reason):
        if not self._valid_id(setup_id):
            return False, "Invalid setup ID"

        if not self._valid_id(order_id):
            return False, "Invalid order ID"

        setup_id = setup_id.strip()
        setup = self.setups.get(setup_id)

        if setup is None:
            return False, "Setup not found"

        if setup["status"] != "OPEN":
            return False, "Setup is already closed"

        if not self._valid_number(exit_price):
            return False, "Invalid exit price"

        if not self._valid_id(reason):
            return False, "Invalid exit reason"

        order = setup["orders"].get(order_id)

        if order is None:
            return False, "Order not found"

        if order["status"] != "OPEN":
            return False, "Order is already closed"

        is_last_open_order = all(
            item["status"] == "CLOSED" or item is order
            for item in setup["orders"].values()
        )

        if is_last_open_order:
            released, message = self.risk_manager.close_position(setup_id)

            if not released:
                return False, f"Risk release failed: {message}"

        order["status"] = "CLOSED"
        order["exit_price"] = float(exit_price)
        order["exit_reason"] = reason.strip()

        if is_last_open_order:
            setup["status"] = "CLOSED"

        return True, "Order closed successfully"

    def close_batch(self, setup_id, exit_price, reason):
        if not self._valid_id(setup_id):
            return False, "Invalid setup ID"

        setup_id = setup_id.strip()
        setup = self.setups.get(setup_id)

        if setup is None:
            return False, "Setup not found"

        if setup["status"] != "OPEN":
            return False, "Setup is already closed"

        if not self._valid_number(exit_price):
            return False, "Invalid exit price"

        if not self._valid_id(reason):
            return False, "Invalid exit reason"

        released, message = self.risk_manager.close_position(setup_id)

        if not released:
            return False, f"Risk release failed: {message}"

        for order in setup["orders"].values():
            if order["status"] == "OPEN":
                order["status"] = "CLOSED"
                order["exit_price"] = float(exit_price)
                order["exit_reason"] = reason.strip()

        setup["status"] = "CLOSED"

        return True, "Batch closed successfully"
