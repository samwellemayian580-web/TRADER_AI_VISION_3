"""TRADER AI VISION 3.0 - Paper trading simulator.

This module is simulation-only. It cannot connect to HFM or MT5.
"""

from dataclasses import dataclass, asdict
import math
from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4


@dataclass
class PaperPosition:
    ticket: str
    symbol: str
    side: str
    volume: float
    entry_price: float
    stop_loss: float
    take_profit: float
    opened_at: str
    status: str = "OPEN"


class PaperBroker:
    MODE = "PAPER"
    LIVE_TRADING = False

    def __init__(self, starting_equity=1000.0):
        if type(starting_equity) not in (int, float) or not math.isfinite(starting_equity) or starting_equity <= 0:
            raise ValueError("Starting equity must be a finite positive number.")

        self._lock = RLock()
        self.balance = float(starting_equity)
        self.equity = float(starting_equity)
        self.positions = {}
        self.history = []

    def get_account(self):
        with self._lock:
            return {
                "mode": self.MODE,
                "live_trading": False,
                "balance": self.balance,
                "equity": self.equity,
                "open_positions": len(self.positions),
            }

    def place_order(
        self,
        symbol,
        side,
        volume,
        entry_price,
        stop_loss,
        take_profit,
    ):
        """Create a simulated position. No broker request is made."""

        side = str(side).upper()

        if symbol != "XAUUSD":
            raise ValueError("Paper broker currently supports XAUUSD only.")

        if side not in ("BUY", "SELL"):
            raise ValueError("Side must be BUY or SELL.")

        values = (volume, entry_price, stop_loss, take_profit)
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
            raise ValueError("Order values must be finite numbers; booleans are not allowed.")

        if any(v <= 0 for v in values):
            raise ValueError("Volume and prices must be positive.")

        if side == "BUY" and not (
            stop_loss < entry_price < take_profit
        ):
            raise ValueError("BUY requires SL < entry < TP.")

        if side == "SELL" and not (
            take_profit < entry_price < stop_loss
        ):
            raise ValueError("SELL requires TP < entry < SL.")

        with self._lock:
            position = PaperPosition(
                ticket=str(uuid4()),
                symbol=symbol,
                side=side,
                volume=float(volume),
                entry_price=float(entry_price),
                stop_loss=float(stop_loss),
                take_profit=float(take_profit),
                opened_at=datetime.now(timezone.utc).isoformat(),
            )

            self.positions[position.ticket] = position
            self.history.append({
                "event": "PAPER_ORDER_OPENED",
                **asdict(position),
            })

            return {
                "success": True,
                "mode": self.MODE,
                "live_trading": False,
                "position": asdict(position),
            }

    def close_position(self, ticket, exit_price):
        """Close a simulated position and calculate simplified P/L."""

        if type(exit_price) not in (int, float) or not math.isfinite(exit_price) or exit_price <= 0:
            raise ValueError("Exit price must be a finite positive number.")

        with self._lock:
            position = self.positions.get(ticket)

            if position is None:
                raise ValueError("Paper position not found.")

            if position.side == "BUY":
                profit = (
                    exit_price - position.entry_price
                ) * position.volume
            else:
                profit = (
                    position.entry_price - exit_price
                ) * position.volume

            self.balance += profit
            self.equity = self.balance

            position.status = "CLOSED"
            closed = asdict(position)
            closed["exit_price"] = float(exit_price)
            closed["profit"] = profit

            del self.positions[ticket]
            self.history.append({
                "event": "PAPER_POSITION_CLOSED",
                **closed,
            })

            return {
                "success": True,
                "mode": self.MODE,
                "live_trading": False,
                "profit": profit,
                "account": self.get_account(),
            }

    def get_positions(self):
        with self._lock:
            return [
                asdict(position)
                for position in self.positions.values()
            ]

    def get_history(self):
        with self._lock:
            return list(self.history)
