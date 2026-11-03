
import csv
import json
import math
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone


BASE_URL = "https://api.twelvedata.com/time_series"
SYMBOL = "XAU/USD"

TIMEFRAMES = {
    "M5": ("5min", 7),
    "M15": ("15min", 14),
    "H1": ("1h", 30),
    "H4": ("4h", 90),
}

START = datetime(2026, 8, 1, tzinfo=timezone.utc)
END = datetime(2026, 11, 2, tzinfo=timezone.utc)


def load_api_key():
    with open(".env", encoding="utf-8") as file:
        for line in file:
            if line.strip().startswith("TWELVE_DATA_API_KEY="):
                key = line.strip().split("=", 1)[1].strip()
                if key:
                    return key.strip("\"'")
    raise RuntimeError("Twelve Data API key not found")


def fetch_chunk(key, interval, start, end):
    params = {
        "symbol": SYMBOL,
        "interval": interval,
        "start_date": start.strftime("%Y-%m-%dT%H:%M:%S"),
        "end_date": end.strftime("%Y-%m-%dT%H:%M:%S"),
        "timezone": "UTC",
        "apikey": key,
    }

    url = BASE_URL + "?" + urllib.parse.urlencode(params)

    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            data = json.loads(response.read().decode())
    except Exception as exc:
        raise RuntimeError(
            "Twelve Data request failed: " + type(exc).__name__
        ) from None

    if data.get("status") != "ok":
        raise RuntimeError(
            "Twelve Data error: " +
            str(data.get("message", data.get("code", "Unknown error")))
        )

    return data.get("values", [])


def download_timeframe(key, timeframe, interval, chunk_days):
    candles = {}

    cursor = START
    total_requests = 0

    while cursor < END:
        next_cursor = min(
            cursor + timedelta(days=chunk_days),
            END
        )

        chunk_end = next_cursor - timedelta(seconds=1)

        print(
            f"{timeframe}: downloading "
            f"{cursor.date()} to {chunk_end.date()}"
        )

        values = fetch_chunk(
            key, interval, cursor, chunk_end
        )

        total_requests += 1

        for item in values:
            timestamp = datetime.fromisoformat(
                item["datetime"]
            )

            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(
                    tzinfo=timezone.utc
                )

            timestamp = timestamp.astimezone(timezone.utc)

            prices = {
                field: float(item[field])
                for field in ("open", "high", "low", "close")
            }

            if not all(
                math.isfinite(value) and value > 0
                for value in prices.values()
            ):
                raise ValueError("Invalid candle price")

            if (
                prices["high"] < max(
                    prices["open"], prices["close"], prices["low"]
                )
                or prices["low"] > min(
                    prices["open"], prices["close"], prices["high"]
                )
            ):
                raise ValueError("Invalid OHLC candle")

            candle = {
                "openTime": timestamp.isoformat(),
                **prices,
                "tickVolume": 0,
            }

            candles[timestamp] = candle

        print("  Received:", len(values),
              "| Unique total:", len(candles))

        cursor = next_cursor
        time.sleep(8)

    ordered = [
        candles[timestamp]
        for timestamp in sorted(candles)
    ]

    if len(ordered) < 60:
        raise RuntimeError(
            f"{timeframe}: insufficient historical data"
        )

    output = f"data/historical/XAUUSD_{timeframe}.json"

    with open(output, "w", encoding="utf-8") as file:
        json.dump(ordered, file, indent=2)

    print(f"\n{timeframe} COMPLETE")
    print("Candles:", len(ordered))
    print("Requests:", total_requests)
    print("Oldest:", ordered[0]["openTime"])
    print("Newest:", ordered[-1]["openTime"])
    print("Saved:", output)

    return len(ordered)


def main():
    key = load_api_key()

    print("TRADER AI 2.0 HISTORICAL DATA DOWNLOADER")
    print("Symbol:", SYMBOL)
    print("Period:", START.date(), "to", END.date())
    print("")

    summary = {}

    for timeframe, settings in TIMEFRAMES.items():
        interval, chunk_days = settings

        summary[timeframe] = download_timeframe(
            key, timeframe, interval, chunk_days
        )

    print("\nALL DOWNLOADS FINISHED")
    print(summary)


if __name__ == "__main__":
    main()
