
import json
from pathlib import Path
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo

SERVER_TZ = ZoneInfo("Europe/Helsinki")

TIMEFRAMES = {
    "M5": 5,
    "M15": 15,
    "H1": 60,
    "H4": 240,
}

SOURCE = Path("data/historical")


def is_tradable_candle(candle, minutes):
    start_utc = datetime.fromisoformat(candle["openTime"])
    start_local = start_utc.astimezone(SERVER_TZ)
    end_local = start_local + timedelta(minutes=minutes)

    # Regular XAUUSD is closed Saturday and Sunday.
    if start_local.weekday() >= 5:
        return False

    # A candle must finish on the same trading day.
    if end_local.date() != start_local.date():
        return False

    weekday = start_local.weekday()

    # Monday opens at 01:05.
    # Tuesday-Friday open at 01:02.
    if weekday == 0:
        session_open = time(1, 5)
    else:
        session_open = time(1, 2)

    # Friday closes at 23:54:59.
    # Other weekdays have the published daily break.
    if weekday == 4:
        session_close = time(23, 54, 59)
    else:
        session_close = time(23, 57, 59)

    candle_start = start_local.time().replace(tzinfo=None)
    candle_end = end_local.time().replace(tzinfo=None)

    return (
        candle_start >= session_open
        and candle_end <= session_close
    )


def main():
    print("HFM XAUUSD SESSION FILTER")
    print("Original files will remain unchanged.\n")

    for tf, minutes in TIMEFRAMES.items():
        source = SOURCE / f"XAUUSD_{tf}.json"
        destination = SOURCE / f"XAUUSD_{tf}_SESSION_PROXY.json"

        candles = json.loads(source.read_text(encoding="utf-8"))

        filtered = [
            candle for candle in candles
            if is_tradable_candle(candle, minutes)
        ]

        excluded = len(candles) - len(filtered)

        if len(filtered) < 60:
            raise RuntimeError(
                f"{tf}: too few candles after filtering"
            )

        destination.write_text(
            json.dumps(filtered, indent=2),
            encoding="utf-8"
        )

        print(f"--- {tf} ---")
        print("Original candles:", len(candles))
        print("Kept candles:", len(filtered))
        print("Excluded candles:", excluded)
        print("First:", filtered[0]["openTime"])
        print("Last:", filtered[-1]["openTime"])
        print("Saved:", destination)
        print()

    print("FILTERING COMPLETE")


if __name__ == "__main__":
    main()
