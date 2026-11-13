
"""TRADER AI VISION 3.0 — Windows MT5 VPS bridge.

Runs on Windows alongside two separately installed MT5 terminals.
Credentials and API token must be supplied through Windows environment
variables, never committed to GitHub.
"""

import hmac
import os
import threading

from flask import Flask, jsonify, request

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

app = Flask(__name__)
LOCK = threading.RLock()

ACCOUNTS = {
    "DEMO": {
        "server": "HFMarketsKE-Demo2",
        "symbol": "XAUUSD",
        "path": os.getenv("MT5_DEMO_PATH", ""),
        "login": os.getenv("MT5_DEMO_LOGIN", ""),
        "password": os.getenv("MT5_DEMO_PASSWORD", ""),
    },
    "LIVE": {
        "server": "HFMarketsKE-Live2",
        "symbol": "XAUUSD",
        "path": os.getenv("MT5_LIVE_PATH", ""),
        "login": os.getenv("MT5_LIVE_LOGIN", ""),
        "password": os.getenv("MT5_LIVE_PASSWORD", ""),
    },
}


class BridgeError(Exception):
    pass


def authenticate():
    expected = os.getenv("MT5_BRIDGE_TOKEN", "")
    supplied = request.headers.get("Authorization", "")

    if not expected or not hmac.compare_digest(
        supplied, "Bearer " + expected
    ):
        return False

    return True


@app.before_request
def require_authentication():
    if not authenticate():
        return jsonify({"error": "Unauthorized"}), 401


def connect_account(mode):
    if mt5 is None:
        raise BridgeError("MetaTrader5 Python package is not installed")

    mode = str(mode).upper()
    if mode not in ACCOUNTS:
        raise BridgeError("Account mode must be DEMO or LIVE")

    config = ACCOUNTS[mode]

    if not all(config[k] for k in ("path", "login", "password")):
        raise BridgeError(mode + " terminal credentials/path not configured")

    mt5.shutdown()

    if not mt5.initialize(
        path=config["path"],
        login=int(config["login"]),
        password=config["password"],
        server=config["server"],
    ):
        raise BridgeError("MT5 initialization failed: " + str(mt5.last_error()))

    account = mt5.account_info()
    if account is None:
        mt5.shutdown()
        raise BridgeError("Could not read MT5 account information")

    if account.server != config["server"]:
        mt5.shutdown()
        raise BridgeError("Connected account server does not match selected profile")

    if not mt5.symbol_select(config["symbol"], True):
        mt5.shutdown()
        raise BridgeError("Could not select XAUUSD")

    return mode, config, account


@app.get("/v1/health")
def health():
    return jsonify({
        "service": "TRADER AI VISION 3 MT5 Bridge",
        "status": "ONLINE",
        "mt5_package_installed": mt5 is not None,
        "accounts_configured": {
            mode: bool(all(
                profile[k] for k in ("path", "login", "password")
            ))
            for mode, profile in ACCOUNTS.items()
        },
        "order_execution": "NOT_ENABLED_IN_INITIAL_BRIDGE",
    })


@app.post("/v1/account")
def account_info():
    data = request.get_json(silent=True) or {}

    try:
        with LOCK:
            mode, config, account = connect_account(data.get("mode", "DEMO"))

            return jsonify({
                "connected": True,
                "mode": mode,
                "server": account.server,
                "symbol": config["symbol"],
                "currency": account.currency,
                "balance": account.balance,
                "equity": account.equity,
                "margin_free": account.margin_free,
                "trade_allowed": account.trade_allowed,
                "execution_enabled": False,
            })
    except (BridgeError, ValueError, TypeError) as exc:
        return jsonify({"connected": False, "error": str(exc)}), 503
    finally:
        if mt5 is not None:
            mt5.shutdown()


@app.post("/v1/quote")
def quote():
    data = request.get_json(silent=True) or {}

    try:
        with LOCK:
            mode, config, account = connect_account(data.get("mode", "DEMO"))
            tick = mt5.symbol_info_tick(config["symbol"])

            if tick is None:
                raise BridgeError("No XAUUSD tick received")

            return jsonify({
                "connected": True,
                "mode": mode,
                "server": account.server,
                "symbol": config["symbol"],
                "bid": tick.bid,
                "ask": tick.ask,
                "last": tick.last,
                "time": tick.time,
            })
    except (BridgeError, ValueError, TypeError) as exc:
        return jsonify({"connected": False, "error": str(exc)}), 503
    finally:
        if mt5 is not None:
            mt5.shutdown()


@app.route("/v1/orders", methods=["POST"])
def orders_not_enabled():
    return jsonify({
        "accepted": False,
        "status": "EXECUTION_NOT_IMPLEMENTED",
        "message": "Order execution will only be enabled after server-side risk validation and demo testing."
    }), 501


@app.route("/v1/orders/<int:ticket>", methods=["PATCH"])
def modify_not_enabled(ticket):
    return jsonify({
        "accepted": False,
        "status": "EXECUTION_NOT_IMPLEMENTED",
        "ticket": ticket,
    }), 501


@app.route("/v1/orders/<int:ticket>/close", methods=["POST"])
def close_not_enabled(ticket):
    return jsonify({
        "accepted": False,
        "status": "EXECUTION_NOT_IMPLEMENTED",
        "ticket": ticket,
    }), 501


@app.get("/")
def root():
    return jsonify({
        "service": "TRADER AI VISION 3 MT5 Bridge",
        "message": "Authenticated API. Use /v1/health."
    })


if __name__ == "__main__":
    # Keep the service on localhost. Put it behind a TLS reverse proxy
    # before allowing connections from outside the Windows VPS.
    app.run(host="127.0.0.1", port=8765, debug=False)
