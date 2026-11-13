"""Twelve Data-backed XAU/USD market feed for TRADER AI 3.0.

This is a REST candle feed, not broker-tick data. Twelve Data updates commodity
prices on its own schedule; do not describe it as an HFM quote or use it to
execute broker orders.
"""
import json
import math
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE_URL = "https://api.twelvedata.com/time_series"
SYMBOL = "XAU/USD"
TIMEFRAMES = {
    "M1": ("1min", 60),
    "M5": ("5min", 300),
    "M15": ("15min", 900),
    "M30": ("30min", 1800),
    "H1": ("1h", 3600),
    "H4": ("4h", 14400),
    "D1": ("1day", 86400),
    "W1": ("1week", 604800),
    "MN1": ("1month", 2592000),
}

# Maximum permitted age of the latest candle's OPEN timestamp.
# These are conservative feed-quality limits, not broker trading hours.
FRESHNESS_LIMIT_SECONDS = {
    "M1": 180,
    "M5": 600,
    "M15": 1800,
    "M30": 3600,
    "H1": 7200,
    "H4": 28800,
    "D1": 172800,
    "W1": 1209600,
    "MN1": 5356800,
}


def _is_stale(timeframe, age_seconds):
    return age_seconds > FRESHNESS_LIMIT_SECONDS[timeframe]


def _load_api_key():
    # Environment variable is preferred for deployment. For local Termux use,
    # read a private .env file in the project root without printing its value.
    key = os.environ.get("TWELVE_DATA_API_KEY", "").strip()
    if key:
        return key
    env_path = Path(os.environ.get("TRADER_AI_ENV_FILE", ".env"))
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("TWELVE_DATA_API_KEY="):
                value = line.split("=", 1)[1].strip().strip("\"'")
                if value:
                    return value
    return None


class MarketDataClient:
    TIMEFRAMES = TIMEFRAMES

    def __init__(self, api_key=None, timeout=20):
        self.api_key = api_key or _load_api_key()
        self.timeout = timeout

    def _get_json(self, params):
        if not self.api_key:
            raise RuntimeError(
                "Twelve Data API key not configured. Set TWELVE_DATA_API_KEY "
                "or add it to the private .env file."
            )
        params = dict(params)
        params.update({
            "symbol": SYMBOL,
            "apikey": self.api_key,
            "timezone": "UTC",
            "format": "JSON",
        })
        url = BASE_URL + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "TRADER-AI-3.0 market-feed"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if payload.get("status") != "ok":
            message = payload.get("message", "Unknown Twelve Data error")
            code = payload.get("code", "")
            raise RuntimeError(f"Twelve Data error {code}: {message}")
        return payload

    def fetch(self, timeframe="M5", limit=200):
        timeframe = str(timeframe).upper()
        if timeframe not in TIMEFRAMES:
            return {"success": False, "status": "INVALID_TIMEFRAME",
                    "signal_allowed": False, "reason": "Use M1, M5, M15, M30, H1, H4, D1, W1 or MN1"}
        if not isinstance(limit, int) or isinstance(limit, bool) or not 60 <= limit <= 5000:
            return {"success": False, "status": "INVALID_LIMIT",
                    "signal_allowed": False, "reason": "Limit must be 60–5000 candles"}

        interval, seconds = TIMEFRAMES[timeframe]
        try:
            payload = self._get_json({
                "interval": interval,
                "outputsize": limit,
            })
            values = payload.get("values")
            if not isinstance(values, list) or len(values) < 60:
                raise RuntimeError("Twelve Data returned fewer than 60 candles")

            candles_by_time = {}
            for item in values:
                raw_dt = item.get("datetime")
                if not raw_dt:
                    continue
                # Twelve Data may return UTC timestamps as ISO or plain datetime.
                try:
                    dt = datetime.fromisoformat(raw_dt.replace("Z", "+00:00"))
                except ValueError:
                    dt = datetime.strptime(raw_dt, "%Y-%m-%d %H:%M:%S")
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                dt = dt.astimezone(timezone.utc)
                prices = {field: float(item[field]) for field in ("open", "high", "low", "close")}
                if not all(math.isfinite(v) and v > 0 for v in prices.values()):
                    raise ValueError("Invalid/non-positive OHLC value")
                if (prices["high"] < max(prices["open"], prices["close"], prices["low"])
                        or prices["low"] > min(prices["open"], prices["close"], prices["high"])):
                    raise ValueError("Inconsistent OHLC candle")
                candles_by_time[dt] = {
                    "openTime": dt.isoformat(),
                    **prices,
                    "tickVolume": int(float(item.get("volume") or 0)),
                }

            candles = [candles_by_time[t] for t in sorted(candles_by_time)]
            if len(candles) < 60:
                raise RuntimeError("Not enough valid candles after validation")

            latest_dt = datetime.fromisoformat(candles[-1]["openTime"])
            age = max(0.0, (datetime.now(timezone.utc) - latest_dt).total_seconds())
            # Age is measured from candle OPEN time, not from a broker tick.
            # Closed sessions may produce stale data; stale data cannot signal.
            stale_after = FRESHNESS_LIMIT_SECONDS[timeframe]
            stale = _is_stale(timeframe, age)
            status = "STALE_DATA" if stale else "LIVE_DATA_READY"
            return {
                "success": True,
                "symbol": "XAU/USD",
                "timeframe": timeframe,
                "provider": "Twelve Data",
                "feed_type": "REST candles (not HFM broker quotes)",
                "status": status,
                "signal_allowed": not stale,
                "latest_candle_open_age_seconds": round(age, 1),
                "latest_candle_age_seconds": round(age, 1),
                "freshness_limit_seconds": stale_after,
                "candles_received": len(candles),
                "latest_price": candles[-1]["close"],
                "candles": candles,
            }
        except Exception as error:
            return {
                "success": False,
                "symbol": "XAU/USD",
                "timeframe": timeframe,
                "provider": "Twelve Data",
                "status": "DATA_ERROR",
                "signal_allowed": False,
                "reason": str(error),
            }
