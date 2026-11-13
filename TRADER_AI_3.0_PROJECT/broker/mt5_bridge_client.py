"""Secure phone-side client for the Windows MT5 VPS bridge."""

import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import (
    HTTPSHandler,
    HTTPRedirectHandler,
    Request,
    build_opener,
)


class BridgeError(RuntimeError):
    """Raised when the VPS bridge request fails."""


class NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class MT5BridgeClient:
    def __init__(self, base_url=None, token=None, timeout=10, opener=None):
        self.base_url = (
            base_url if base_url is not None
            else os.getenv("MT5_BRIDGE_URL", "")
        ).rstrip("/")
        self.token = (
            token if token is not None
            else os.getenv("MT5_BRIDGE_TOKEN", "")
        )
        self.timeout = timeout
        self.connected = False
        self.execution_enabled = False
        self.opener = opener or build_opener(
            HTTPSHandler(), NoRedirectHandler()
        )

    def configuration_status(self):
        if not self.base_url or not self.token:
            return {
                "configured": False,
                "connected": False,
                "execution_enabled": False,
                "message": "VPS bridge credentials are not configured.",
            }

        parsed = urlparse(self.base_url)
        if parsed.scheme != "https":
            return {
                "configured": False,
                "connected": False,
                "execution_enabled": False,
                "message": "Bridge URL must use HTTPS.",
            }

        if (
            not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            return {
                "configured": False,
                "connected": False,
                "execution_enabled": False,
                "message": "Invalid bridge URL.",
            }

        return {
            "configured": True,
            "connected": False,
            "execution_enabled": False,
            "message": "Configuration ready. VPS connection not tested.",
        }

    def _send(self, method, path, body=None):
        config = self.configuration_status()
        if not config["configured"]:
            raise BridgeError(config["message"])

        headers = {
            "Authorization": "Bearer " + self.token,
            "Accept": "application/json",
        }

        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = Request(
            self.base_url + path,
            data=data,
            headers=headers,
            method=method,
        )

        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                raw = response.read()
        except HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8")
            except Exception:
                detail = str(exc)
            raise BridgeError(
                f"VPS bridge returned HTTP {exc.code}: {detail}"
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise BridgeError(
                f"Could not reach VPS bridge: {exc}"
            ) from exc

        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BridgeError("VPS bridge returned invalid JSON.") from exc

        if not isinstance(payload, dict):
            raise BridgeError("Unexpected bridge response.")

        if payload.get("success") is not True:
            raise BridgeError(
                str(payload.get("error", "Bridge request failed."))
            )

        return payload

    def _request(self, path):
        return self._send("GET", path)

    def get_health(self):
        return self._request("/api/v1/health")

    def get_mt5_status(self):
        payload = self._request("/api/v1/mt5/status")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise BridgeError("Invalid MT5 status response.")
        self.connected = bool(data.get("terminal_connected"))
        return data

    def get_account(self):
        payload = self._request("/api/v1/mt5/account")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise BridgeError("Invalid MT5 account response.")
        return data

    def get_positions(self, symbol="XAUUSD"):
        if symbol != "XAUUSD":
            raise BridgeError("Only XAUUSD is enabled.")
        payload = self._request("/api/v1/mt5/positions")
        data = payload.get("data")
        if not isinstance(data, list):
            raise BridgeError("Invalid MT5 positions response.")
        return data

    def get_quote(self, symbol="XAUUSD"):
        if symbol != "XAUUSD":
            raise BridgeError("Only XAUUSD is enabled.")
        payload = self._request("/api/v1/mt5/quote/" + symbol)
        data = payload.get("data")
        if not isinstance(data, dict):
            raise BridgeError("Invalid MT5 quote response.")
        return data

    def place_order(self, order):
        required = {
            "request_id", "symbol", "side",
            "volume", "stop_loss", "take_profit",
        }
        if not isinstance(order, dict) or set(order) != required:
            raise BridgeError("Invalid order request fields.")
        if order["symbol"] != "XAUUSD":
            raise BridgeError("Only XAUUSD is enabled.")
        if (
            not isinstance(order["request_id"], str)
            or not order["request_id"].strip()
        ):
            raise BridgeError("A valid request_id is required.")

        return self._send("POST", "/api/v1/mt5/order", order)

    def place_batch(self, setup_id, batch, take_profit):
        if not isinstance(setup_id, str) or not setup_id.strip():
            raise BridgeError("A valid setup_id is required.")
        if not isinstance(batch, dict) or batch.get("approved") is not True:
            raise BridgeError("Only an approved batch can be submitted.")
        if batch.get("side") not in ("BUY", "SELL"):
            raise BridgeError("Invalid batch side.")
        if not isinstance(batch.get("orders"), list) or not batch["orders"]:
            raise BridgeError("Batch must contain child orders.")

        body = {
            "setup_id": setup_id,
            "batch": batch,
            "take_profit": take_profit,
        }
        return self._send("POST", "/api/v1/mt5/batch", body)

    def check_connection(self):
        self.connected = False
        try:
            self.get_health()
            status = self.get_mt5_status()
            return {
                "configured": True,
                "connected": self.connected,
                "execution_enabled": False,
                "live_trading": False,
                "mt5": status,
                "message": "VPS bridge connection successful.",
            }
        except BridgeError as exc:
            return {
                "configured": self.configuration_status()["configured"],
                "connected": False,
                "execution_enabled": False,
                "live_trading": False,
                "message": str(exc),
            }

    def get_status(self):
        return {
            "mode": "VPS_BRIDGE",
            "configured": self.configuration_status()["configured"],
            "connected": self.connected,
            "execution_enabled": False,
            "live_trading": False,
            "message": "No execution has been enabled.",
        }
