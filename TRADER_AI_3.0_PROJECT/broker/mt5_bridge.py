
"""Secure MT5 VPS bridge client for TRADER AI VISION 3.

The actual MT5 terminal and server-side bridge run on Windows VPS.
This client fails closed if the bridge is unavailable or unauthenticated.
"""

import json
import os
import urllib.error
import urllib.request
from urllib.parse import urlparse

from broker.mt5_config import get_account


class MT5BridgeError(RuntimeError):
    pass


class MT5Bridge:
    def __init__(self, timeout=10):
        self.base_url = os.getenv("MT5_BRIDGE_URL", "").rstrip("/")
        self.token = os.getenv("MT5_BRIDGE_TOKEN", "")
        self.timeout = timeout

        if not self.base_url:
            raise MT5BridgeError("MT5 VPS bridge URL is not configured")

        parsed = urlparse(self.base_url)

        if parsed.scheme != "https":
            if not (
                parsed.scheme == "http"
                and parsed.hostname in ("localhost", "127.0.0.1")
            ):
                raise MT5BridgeError("Bridge must use HTTPS")

        if not self.token:
            raise MT5BridgeError("MT5 bridge authentication token is missing")

    def _request(self, method, path, payload=None, request_id=None):
        url = self.base_url + path

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        if request_id:
            headers["Idempotency-Key"] = request_id

        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=body,
            headers=headers,
            method=method,
        )

        try:
            with urllib.request.urlopen(
                req, timeout=self.timeout
            ) as response:
                result = json.loads(response.read().decode("utf-8"))

                if not isinstance(result, dict):
                    raise MT5BridgeError("Invalid bridge response")

                return result

        except urllib.error.HTTPError as exc:
            raise MT5BridgeError(
                f"Bridge rejected request: HTTP {exc.code}"
            ) from exc

        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise MT5BridgeError(
                "MT5 VPS bridge is unreachable"
            ) from exc

        except (ValueError, UnicodeDecodeError) as exc:
            raise MT5BridgeError(
                "Bridge returned invalid JSON"
            ) from exc

    def health(self):
        return self._request("GET", "/v1/health")

    def account(self, mode="DEMO"):
        profile = get_account(mode)
        return self._request(
            "POST",
            "/v1/account",
            {"mode": profile["mode"], "server": profile["server"]},
        )

    def quote(self, mode="DEMO"):
        profile = get_account(mode)
        return self._request(
            "POST",
            "/v1/quote",
            {"mode": profile["mode"], "symbol": profile["symbol"]},
        )

    def submit_order(self, mode, order, request_id):
        if not request_id:
            raise MT5BridgeError("Unique order request ID is required")

        profile = get_account(mode)

        if not isinstance(order, dict):
            raise MT5BridgeError("Order must be a dictionary")

        payload = {
            "mode": profile["mode"],
            "server": profile["server"],
            "symbol": profile["symbol"],
            "order": order,
        }

        return self._request(
            "POST",
            "/v1/orders",
            payload,
            request_id=request_id,
        )

    def modify_order(self, mode, ticket, changes):
        profile = get_account(mode)
        return self._request(
            "PATCH",
            f"/v1/orders/{int(ticket)}",
            {
                "mode": profile["mode"],
                "server": profile["server"],
                "changes": changes,
            },
        )

    def close_order(self, mode, ticket, request_id):
        if not request_id:
            raise MT5BridgeError("Unique close request ID is required")

        profile = get_account(mode)
        return self._request(
            "POST",
            f"/v1/orders/{int(ticket)}/close",
            {
                "mode": profile["mode"],
                "server": profile["server"],
            },
            request_id=request_id,
        )
