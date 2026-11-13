"""TRADER AI VISION 3.0 - Windows VPS MT5 bridge.

Read-only bridge for initial HFM demo verification.
No order placement or modification endpoints exist.
"""

import hmac
import os
import sqlite3
import json
import hashlib
import time

from flask import Flask, jsonify, request
from broker.mt5_execution import MT5ExecutionEngine, ExecutionError
from broker.mt5_batch_execution import MT5BatchExecutionEngine
from deployment.windows_vps.broker_reconciliation import (
    get_symbol_specifications,
    reconcile_positions,
)


class MT5Terminal:

    def __init__(self, mt5_module=None):
        self.mt5 = mt5_module

    def _load(self):
        if self.mt5 is None:
            try:
                import MetaTrader5
                self.mt5 = MetaTrader5
            except ImportError as exc:
                raise RuntimeError(
                    "MetaTrader5 package is not installed."
                ) from exc

        return self.mt5

    def connect(self):
        mt5 = self._load()

        if not mt5.initialize():
            raise RuntimeError(
                f"MT5 initialization failed: {mt5.last_error()}"
            )

        terminal = mt5.terminal_info()
        account = mt5.account_info()

        if terminal is None or account is None:
            raise RuntimeError(
                "MT5 terminal or account information unavailable."
            )

        return mt5, terminal, account

    def status(self):
        mt5, terminal, account = self.connect()

        return {
            "terminal_connected": bool(terminal.connected),
            "account_connected": account is not None,
            "trade_allowed": bool(terminal.trade_allowed),
            "account_trade_allowed": bool(account.trade_allowed),
            "server": str(account.server),
            "currency": str(account.currency),
            "mode": "READ_ONLY",
            "live_execution_enabled": False,
        }

    def account(self):
        _, _, account = self.connect()

        return {
            "balance": float(account.balance),
            "equity": float(account.equity),
            "currency": str(account.currency),
            "leverage": int(account.leverage),
            "trade_mode": int(getattr(account, "trade_mode", -1)),
            "is_real_account": (
                getattr(account, "trade_mode", None)
                == getattr(self._load(), "ACCOUNT_TRADE_MODE_REAL", 2)
            ),
            "trade_allowed": bool(account.trade_allowed),
            "mode": "READ_ONLY",
        }

    def positions(self, symbol="XAUUSD"):
        if symbol != "XAUUSD":
            raise RuntimeError("Only XAUUSD is enabled.")

        mt5, _, _ = self.connect()
        positions = mt5.positions_get(symbol=symbol)

        if positions is None:
            raise RuntimeError(
                f"Could not retrieve MT5 positions: {mt5.last_error()}"
            )

        return [
            {
                "ticket": int(position.ticket),
                "symbol": str(position.symbol),
                "type": int(position.type),
                "volume": float(position.volume),
                "price_open": float(position.price_open),
                "price_current": float(position.price_current),
                "stop_loss": float(position.sl),
                "take_profit": float(position.tp),
                "profit": float(position.profit),
                "magic": int(position.magic),
            }
            for position in positions
        ]

    def quote(self, symbol):
        mt5, _, _ = self.connect()

        info = mt5.symbol_info(symbol)
        tick = mt5.symbol_info_tick(symbol)

        if info is None or tick is None:
            raise RuntimeError(
                f"Symbol unavailable: {symbol}"
            )

        return {
            "symbol": symbol,
            "bid": float(tick.bid),
            "ask": float(tick.ask),
            "time": int(tick.time),
            "digits": int(info.digits),
            "point": float(info.point),
            "contract_size": float(info.trade_contract_size),
            "volume_min": float(info.volume_min),
            "volume_max": float(info.volume_max),
            "volume_step": float(info.volume_step),
            "volume_limit": float(getattr(info, "volume_limit", 0.0) or 0.0),
            "tick_size": float(getattr(info, "trade_tick_size", 0.0) or 0.0),
            "tick_value": float(getattr(info, "trade_tick_value", 0.0) or 0.0),
            "tick_value_profit": float(getattr(info, "trade_tick_value_profit", 0.0) or 0.0),
            "tick_value_loss": float(getattr(info, "trade_tick_value_loss", 0.0) or 0.0),
            "stops_level": int(getattr(info, "trade_stops_level", 0) or 0),
            "freeze_level": int(getattr(info, "trade_freeze_level", 0) or 0),
            "trade_mode": int(getattr(info, "trade_mode", 0) or 0),
            "currency_base": str(getattr(info, "currency_base", "") or ""),
            "currency_profit": str(getattr(info, "currency_profit", "") or ""),
            "currency_margin": str(getattr(info, "currency_margin", "") or ""),
            "mode": "READ_ONLY",
        }


def create_app(token=None, mt5_module=None):
    app = Flask(__name__)

    bridge_token = token or os.getenv("MT5_BRIDGE_TOKEN", "")
    terminal = MT5Terminal(mt5_module)

    @app.before_request
    def authenticate():
        if not bridge_token:
            return jsonify({
                "success": False,
                "error": "Bridge authentication is not configured."
            }), 503

        supplied = request.headers.get("Authorization", "")
        expected = "Bearer " + bridge_token

        if not hmac.compare_digest(supplied, expected):
            return jsonify({
                "success": False,
                "error": "Authentication failed."
            }), 401

    @app.route("/api/v1/health", methods=["GET"])
    def health():
        return jsonify({
            "success": True,
            "service": "TRADER AI MT5 VPS Bridge",
            "mode": "READ_ONLY",
            "live_execution_enabled": False,
        })

    @app.route("/api/v1/mt5/status", methods=["GET"])
    def mt5_status():
        try:
            return jsonify({
                "success": True,
                "data": terminal.status()
            })
        except Exception as exc:
            return jsonify({
                "success": False,
                "error": str(exc)
            }), 503

    @app.route("/api/v1/mt5/account", methods=["GET"])
    def mt5_account():
        try:
            return jsonify({
                "success": True,
                "data": terminal.account()
            })
        except Exception as exc:
            return jsonify({
                "success": False,
                "error": str(exc)
            }), 503

    @app.route("/api/v1/mt5/positions", methods=["GET"])
    def mt5_positions():
        try:
            return jsonify({
                "success": True,
                "data": terminal.positions("XAUUSD")
            })
        except Exception as exc:
            return jsonify({
                "success": False,
                "error": str(exc)
            }), 503

    @app.route("/api/v1/mt5/quote/<symbol>", methods=["GET"])
    def mt5_quote(symbol):
        if symbol != "XAUUSD":
            return jsonify({
                "success": False,
                "error": "Only XAUUSD is enabled."
            }), 400

        try:
            return jsonify({
                "success": True,
                "data": terminal.quote(symbol)
            })
        except Exception as exc:
            return jsonify({
                "success": False,
                "error": str(exc)
            }), 503


    @app.route("/api/v1/mt5/order", methods=["POST"])
    def mt5_order():
        if os.getenv("MT5_ORDER_API_ENABLED") != "YES":
            return jsonify({
                "success": False,
                "error": "Order API is disabled."
            }), 423

        if os.getenv("MT5_LIVE_EXECUTION_ENABLED") != "YES":
            return jsonify({
                "success": False,
                "error": "Live execution is disabled."
            }), 423

        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify({"success": False, "error": "JSON body required."}), 400

        required = {"request_id", "symbol", "side", "volume", "stop_loss", "take_profit"}
        if set(body) != required:
            return jsonify({
                "success": False,
                "error": "Required fields: request_id, symbol, side, volume, stop_loss, take_profit."
            }), 400

        request_id = body["request_id"]
        if not isinstance(request_id, str) or not request_id.strip() or len(request_id) > 128:
            return jsonify({"success": False, "error": "Invalid request_id."}), 400

        payload = {key: body[key] for key in sorted(required) if key != "request_id"}
        payload_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

        db_path = os.getenv("MT5_IDEMPOTENCY_DB", "trader_ai_orders.sqlite3")

        try:
            with sqlite3.connect(db_path, timeout=10) as db:
                db.execute("""
                    CREATE TABLE IF NOT EXISTS order_requests (
                        request_id TEXT PRIMARY KEY,
                        payload_hash TEXT NOT NULL,
                        state TEXT NOT NULL,
                        response TEXT,
                        created_at REAL NOT NULL
                    )
                """)
                db.commit()

                cursor = db.execute(
                    "INSERT OR IGNORE INTO order_requests "
                    "(request_id, payload_hash, state, created_at) "
                    "VALUES (?, ?, 'PROCESSING', ?)",
                    (request_id, payload_hash, time.time())
                )
                db.commit()

                if cursor.rowcount == 0:
                    row = db.execute(
                        "SELECT payload_hash, state, response "
                        "FROM order_requests WHERE request_id = ?",
                        (request_id,)
                    ).fetchone()

                    if row[0] != payload_hash:
                        return jsonify({
                            "success": False,
                            "error": "Request ID was already used with different order data."
                        }), 409

                    if row[1] == "COMPLETE" and row[2]:
                        return jsonify(json.loads(row[2])), 200

                    return jsonify({
                        "success": False,
                        "error": "This request is already processing or has an uncertain outcome. Reconcile with MT5 before retrying."
                    }), 409

            # Only the VPS creates and uses the MT5 execution engine.
            engine = MT5ExecutionEngine(terminal.connect()[0])
            result = engine.place_market_order(
                symbol=body["symbol"],
                side=body["side"],
                volume=body["volume"],
                stop_loss=body["stop_loss"],
                take_profit=body["take_profit"],
            )

            response = {"success": True, "data": result}

            with sqlite3.connect(db_path, timeout=10) as db:
                db.execute(
                    "UPDATE order_requests SET state='COMPLETE', response=? "
                    "WHERE request_id=?",
                    (json.dumps(response), request_id)
                )
                db.commit()

            return jsonify(response), 200

        except Exception as exc:
            # Never automatically retry an order with an uncertain outcome.
            try:
                with sqlite3.connect(db_path, timeout=10) as db:
                    db.execute(
                        "UPDATE order_requests SET state='UNKNOWN' WHERE request_id=?",
                        (request_id,)
                    )
                    db.commit()
            except Exception:
                pass

            return jsonify({
                "success": False,
                "error": str(exc),
                "request_id": request_id,
                "reconciliation_required": True
            }), 503


    @app.route("/api/v1/mt5/batch", methods=["POST"])
    def mt5_batch():
        if os.getenv("MT5_BATCH_API_ENABLED") != "YES":
            return jsonify({
                "success": False,
                "error": "Batch API is disabled."
            }), 423

        body = request.get_json(silent=True)
        if not isinstance(body, dict) or set(body) != {
            "setup_id", "batch", "take_profit"
        }:
            return jsonify({
                "success": False,
                "error": "Required fields: setup_id, batch, take_profit."
            }), 400

        setup_id = body["setup_id"]
        batch = body["batch"]

        if (not isinstance(setup_id, str) or not setup_id.strip()
                or len(setup_id) > 128):
            return jsonify({"success": False, "error": "Invalid setup_id."}), 400

        if not isinstance(batch, dict):
            return jsonify({"success": False, "error": "Invalid batch data."}), 400

        db_path = os.getenv("MT5_IDEMPOTENCY_DB", "trader_ai_orders.sqlite3")
        payload_hash = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

        try:
            # Reserve one of the five setup slots durably before execution.
            with sqlite3.connect(db_path, timeout=15) as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("""
                    CREATE TABLE IF NOT EXISTS batch_requests (
                        setup_id TEXT PRIMARY KEY,
                        payload_hash TEXT NOT NULL,
                        mode TEXT NOT NULL,
                        state TEXT NOT NULL,
                        response TEXT,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL
                    )
                """)
                db.execute("""
                    CREATE TABLE IF NOT EXISTS batch_children (
                        setup_id TEXT NOT NULL,
                        child_number INTEGER NOT NULL,
                        state TEXT NOT NULL,
                        ticket INTEGER,
                        deal INTEGER,
                        volume REAL,
                        risk_cash REAL,
                        response TEXT,
                        PRIMARY KEY (setup_id, child_number)
                    )
                """)

                existing = db.execute(
                    "SELECT payload_hash, state, response FROM batch_requests "
                    "WHERE setup_id = ?", (setup_id,)
                ).fetchone()

                if existing:
                    db.rollback()
                    if existing[0] != payload_hash:
                        return jsonify({
                            "success": False,
                            "error": "Setup ID already exists with different data."
                        }), 409
                    if existing[1] == "SUBMITTED" and existing[2]:
                        return jsonify(json.loads(existing[2])), 200
                    return jsonify({
                        "success": False,
                        "state": existing[1],
                        "error": "This setup already exists. Reconciliation is required; do not retry it."
                    }), 409

                active = db.execute("""
                    SELECT COUNT(*) FROM batch_requests
                    WHERE state IN ('PROCESSING', 'PARTIAL', 'UNKNOWN', 'SUBMITTED')
                """).fetchone()[0]

                if active >= 5:
                    db.rollback()
                    return jsonify({
                        "success": False,
                        "error": "Five active or unresolved setups already exist."
                    }), 409

                now = time.time()
                mode = os.getenv("MT5_EXECUTION_MODE", "LIVE").strip().upper()
                db.execute("""
                    INSERT INTO batch_requests
                    (setup_id, payload_hash, mode, state, created_at, updated_at)
                    VALUES (?, ?, ?, 'PROCESSING', ?, ?)
                """, (setup_id, payload_hash, mode, now, now))

                orders = batch.get("orders")
                if isinstance(orders, list):
                    for number, child in enumerate(orders, start=1):
                        db.execute("""
                            INSERT INTO batch_children
                            (setup_id, child_number, state, volume, risk_cash)
                            VALUES (?, ?, 'PENDING', ?, ?)
                        """, (
                            setup_id, number,
                            child.get("lot") if isinstance(child, dict) else None,
                            child.get("estimated_risk") if isinstance(child, dict) else None,
                        ))
                db.commit()

            engine = MT5BatchExecutionEngine(terminal.connect()[0])
            result = engine.place_batch(
                setup_id, batch, body["take_profit"]
            )

            state = result.get("state", "UNKNOWN")
            response = {"success": bool(result.get("success")), "data": result}

            with sqlite3.connect(db_path, timeout=15) as db:
                db.execute("""
                    UPDATE batch_requests
                    SET state=?, response=?, updated_at=?
                    WHERE setup_id=?
                """, (state, json.dumps(response), time.time(), setup_id))

                children = (
                    result.get("children")
                    or result.get("completed_children")
                    or []
                )
                for child in children:
                    number = child.get("child")
                    if number is None:
                        continue
                    db.execute("""
                        UPDATE batch_children
                        SET state='SUBMITTED', ticket=?, deal=?,
                            volume=?, risk_cash=?, response=?
                        WHERE setup_id=? AND child_number=?
                    """, (
                        child.get("ticket"), child.get("deal"),
                        child.get("filled_volume", child.get("requested_volume")),
                        child.get("risk_cash_estimate"),
                        json.dumps(child), setup_id, number
                    ))
                db.commit()

            return jsonify(response), 200 if result.get("success") else 503

        except Exception as exc:
            # Keep the reservation UNKNOWN after any uncertain outcome.
            try:
                with sqlite3.connect(db_path, timeout=15) as db:
                    db.execute("""
                        UPDATE batch_requests
                        SET state='UNKNOWN', updated_at=?
                        WHERE setup_id=?
                    """, (time.time(), setup_id))
                    db.commit()
            except Exception:
                pass

            return jsonify({
                "success": False,
                "error": str(exc),
                "setup_id": setup_id,
                "reconciliation_required": True
            }), 503


    @app.route("/api/v1/mt5/reconciliation", methods=["GET"])
    def mt5_reconciliation():
        try:
            mt5, _, account = terminal.connect()

            specs = get_symbol_specifications(mt5, "XAUUSD")
            snapshot = reconcile_positions(mt5, "XAUUSD")

            return jsonify({
                "success": True,
                "data": {
                    "server": str(account.server),
                    "account_trade_allowed": bool(account.trade_allowed),
                    "symbol_specifications": specs,
                    "reconciliation": snapshot,
                    "new_execution_allowed": False,
                },
            })
        except Exception as exc:
            return jsonify({
                "success": False,
                "error": str(exc),
                "new_execution_allowed": False,
            }), 503

    return app


if __name__ == "__main__":
    secret = os.getenv("MT5_BRIDGE_TOKEN", "")

    if not secret:
        raise SystemExit(
            "Set MT5_BRIDGE_TOKEN before starting the bridge."
        )

    service = create_app(token=secret)

    # Localhost only until a secure VPN/reverse proxy is configured.
    service.run(
        host="127.0.0.1",
        port=8765,
        debug=False
    )
