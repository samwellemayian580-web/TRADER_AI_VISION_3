import pandas as pd
import numpy as np


class MarketAnalyzer:

    def analyze(self, candles):
        required = ["open", "high", "low", "close"]

        if candles is None:
            return {"decision": "WAIT", "reason": "No candle data"}

        try:
            df = pd.DataFrame(candles).copy()
            df.columns = [str(c).lower() for c in df.columns]

            if not all(col in df.columns for col in required):
                return {
                    "decision": "WAIT",
                    "reason": "Missing OHLC candle columns"
                }

            for col in required:
                df[col] = pd.to_numeric(df[col], errors="coerce")

            df = df.dropna(subset=required)

            if len(df) < 60:
                return {
                    "decision": "WAIT",
                    "reason": "At least 60 valid candles are required",
                    "candles_received": len(df)
                }

            if not np.isfinite(df[required].to_numpy()).all():
                return {
                    "decision": "WAIT",
                    "reason": "Invalid candle values"
                }

            if (
                (df["high"] < df["low"]).any()
                or (df["high"] < df["open"]).any()
                or (df["high"] < df["close"]).any()
                or (df["low"] > df["open"]).any()
                or (df["low"] > df["close"]).any()
            ):
                return {
                    "decision": "WAIT",
                    "reason": "Inconsistent OHLC candle data"
                }

            close = df["close"]
            previous_close = close.shift(1)

            df["ema20"] = close.ewm(
                span=20, adjust=False
            ).mean()

            df["ema50"] = close.ewm(
                span=50, adjust=False
            ).mean()

            change = close.diff()
            gain = change.clip(lower=0)
            loss = -change.clip(upper=0)

            avg_gain = gain.ewm(
                alpha=1/14, adjust=False, min_periods=14
            ).mean()

            avg_loss = loss.ewm(
                alpha=1/14, adjust=False, min_periods=14
            ).mean()

            rs = avg_gain / avg_loss.replace(0, np.nan)
            df["rsi"] = 100 - (100 / (1 + rs))

            rsi_fallback = pd.Series(
                np.where(avg_gain > 0, 100.0, 50.0),
                index=df.index
            )

            df["rsi"] = df["rsi"].fillna(rsi_fallback)

            true_range = pd.concat([
                df["high"] - df["low"],
                (df["high"] - previous_close).abs(),
                (df["low"] - previous_close).abs()
            ], axis=1).max(axis=1)

            df["atr"] = true_range.ewm(
                alpha=1/14, adjust=False
            ).mean()

            latest = df.iloc[-1]
            previous = df.iloc[-2]

            bullish_engulfing = (
                previous["close"] < previous["open"]
                and latest["close"] > latest["open"]
                and latest["open"] <= previous["close"]
                and latest["close"] >= previous["open"]
            )

            bearish_engulfing = (
                previous["close"] > previous["open"]
                and latest["close"] < latest["open"]
                and latest["open"] >= previous["close"]
                and latest["close"] <= previous["open"]
            )

            body = abs(latest["close"] - latest["open"])
            candle_range = latest["high"] - latest["low"]

            if candle_range <= 0:
                return {
                    "decision": "WAIT",
                    "reason": "Invalid latest candle range"
                }

            upper_wick = (
                latest["high"] -
                max(latest["open"], latest["close"])
            )

            lower_wick = (
                min(latest["open"], latest["close"]) -
                latest["low"]
            )

            hammer = (
                lower_wick >= body * 2
                and upper_wick <= max(body, candle_range * 0.1)
                and body / candle_range <= 0.4
            )

            shooting_star = (
                upper_wick >= body * 2
                and lower_wick <= max(body, candle_range * 0.1)
                and body / candle_range <= 0.4
            )

            patterns = []

            if bullish_engulfing:
                patterns.append("BULLISH_ENGULFING")

            if bearish_engulfing:
                patterns.append("BEARISH_ENGULFING")

            if hammer:
                patterns.append("HAMMER")

            if shooting_star:
                patterns.append("SHOOTING_STAR")

            bullish_trend = (
                latest["ema20"] > latest["ema50"]
                and latest["close"] > latest["ema20"]
            )

            bearish_trend = (
                latest["ema20"] < latest["ema50"]
                and latest["close"] < latest["ema20"]
            )

            bullish_confirmation = (
                bullish_engulfing or hammer
            )

            bearish_confirmation = (
                bearish_engulfing or shooting_star
            )

            decision = "WAIT"
            reason = "No confirmed trend and candle setup"

            if (
                bullish_trend
                and bullish_confirmation
                and 50 <= latest["rsi"] < 70
            ):
                decision = "BUY_SETUP"
                reason = "Bullish trend with candle confirmation"

            elif (
                bearish_trend
                and bearish_confirmation
                and 30 < latest["rsi"] <= 50
            ):
                decision = "SELL_SETUP"
                reason = "Bearish trend with candle confirmation"

            return {
                "decision": decision,
                "reason": reason,
                "trend": (
                    "BULLISH" if bullish_trend
                    else "BEARISH" if bearish_trend
                    else "SIDEWAYS_OR_UNCONFIRMED"
                ),
                "close": round(float(latest["close"]), 3),
                "ema20": round(float(latest["ema20"]), 3),
                "ema50": round(float(latest["ema50"]), 3),
                "rsi14": round(float(latest["rsi"]), 2),
                "atr14": round(float(latest["atr"]), 3),
                "patterns": patterns,
                "candles_analyzed": len(df),
                "execution_authorized": False
            }

        except Exception as error:
            return {
                "decision": "WAIT",
                "reason": "Analysis error: " + str(error)
            }
