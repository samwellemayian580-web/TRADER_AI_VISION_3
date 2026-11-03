import json
from pathlib import Path
from datetime import datetime, timedelta
from bisect import bisect_right


class HistoricalDataAdapter:
    """
    Loads Twelve Data session-filtered XAU/USD candles
    and provides only candles completed by the requested time.

    This is historical proxy data, not verified HFM pricing.
    """

    BASE_DIR = Path(__file__).resolve().parent / "historical"

    TIMEFRAMES = {
        "M5": ("XAUUSD_M5_SESSION_PROXY.json", 5),
        "M15": ("XAUUSD_M15_SESSION_PROXY.json", 15),
        "H1": ("XAUUSD_H1_SESSION_PROXY.json", 60),
        "H4": ("XAUUSD_H4_SESSION_PROXY.json", 240),
    }

    def __init__(self):
        self.data = {}
        self.close_times = {}
        self.load_all()

    @staticmethod
    def parse_time(value):
        timestamp = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )

        if timestamp.tzinfo is None:
            raise ValueError("Candle timestamp must include timezone")

        return timestamp

    def load_all(self):
        for timeframe, (filename, minutes) in self.TIMEFRAMES.items():
            path = self.BASE_DIR / filename

            if not path.exists():
                raise FileNotFoundError(
                    f"Historical file missing: {path}"
                )

            with open(path, "r", encoding="utf-8") as file:
                candles = json.load(file)

            if not isinstance(candles, list):
                raise ValueError(f"{timeframe} data must be a list")

            if not candles:
                raise ValueError(f"{timeframe} dataset is empty")

            prepared = []
            closing_times = []

            for candle in candles:
                if not isinstance(candle, dict):
                    raise ValueError(f"Invalid {timeframe} candle")

                required = ["openTime", "open", "high", "low", "close"]

                if not all(key in candle for key in required):
                    raise ValueError(
                        f"{timeframe} candle is missing required fields"
                    )

                open_time = self.parse_time(candle["openTime"])
                close_time = open_time + timedelta(minutes=minutes)

                prices = [
                    float(candle["open"]),
                    float(candle["high"]),
                    float(candle["low"]),
                    float(candle["close"]),
                ]

                o, h, l, c = prices

                if not all(
                    price > 0 and price < float("inf")
                    for price in prices
                ):
                    raise ValueError(f"Invalid {timeframe} prices")

                if h < max(o, c) or l > min(o, c) or h < l:
                    raise ValueError(f"Inconsistent {timeframe} OHLC")

                item = dict(candle)
                item["open"] = o
                item["high"] = h
                item["low"] = l
                item["close"] = c
                item["_open_time"] = open_time
                item["_close_time"] = close_time

                prepared.append(item)
                closing_times.append(close_time)

            if closing_times != sorted(closing_times):
                raise ValueError(f"{timeframe} candles are not chronological")

            if len(set(closing_times)) != len(closing_times):
                raise ValueError(f"{timeframe} contains duplicate candles")

            self.data[timeframe] = prepared
            self.close_times[timeframe] = closing_times

        print("Historical datasets loaded successfully.")

        for timeframe in self.TIMEFRAMES:
            print(
                f"{timeframe}: {len(self.data[timeframe])} candles"
            )

    def get_snapshot(self, decision_time, max_candles=None):
        """
        Return only candles whose closing time is <= decision_time.
        """

        if isinstance(decision_time, str):
            decision_time = self.parse_time(decision_time)

        if decision_time.tzinfo is None:
            raise ValueError("Decision time must include timezone")

        snapshot = {}

        for timeframe in self.TIMEFRAMES:
            candles = self.data[timeframe]
            close_times = self.close_times[timeframe]

            end_index = bisect_right(close_times, decision_time)

            completed = candles[:end_index]
            if max_candles is not None:
                completed = completed[-max_candles:]


            snapshot[timeframe] = {
                "success": True,
                "signal_allowed": True,
                "status": "LIVE_DATA_READY",
                "source": "TWELVE_DATA_SESSION_FILTERED_PROXY",
                "decision_time": decision_time.isoformat(),
                "candles": [
                    {
                        key: value
                        for key, value in candle.items()
                        if not key.startswith("_")
                    }
                    for candle in completed
                ],
            }

        return snapshot

    def get_decision_times(self):
        """
        Use completed M5 candle closing times as decision times.
        """

        return list(self.close_times["M5"])

    def verify_no_future_candles(self, snapshot, decision_time):
        if isinstance(decision_time, str):
            decision_time = self.parse_time(decision_time)

        for timeframe, dataset in snapshot.items():
            for candle in dataset["candles"]:
                open_time = self.parse_time(candle["openTime"])
                minutes = self.TIMEFRAMES[timeframe][1]
                close_time = open_time + timedelta(minutes=minutes)

                if close_time > decision_time:
                    return False

        return True
