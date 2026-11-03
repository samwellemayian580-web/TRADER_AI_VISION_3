from analysis.market_analyzer import MarketAnalyzer


class MultiTimeframeAnalyzer:

    TIMEFRAMES = ["M5", "M15", "H1", "H4"]

    def __init__(self, cache_enabled=False):
        self.analyzer = MarketAnalyzer()
        self.cache_enabled = cache_enabled
        self._cache = {}

    @staticmethod
    def _cache_key(candles):
        if not candles:
            return None

        first = candles[0]
        last = candles[-1]

        return (
            len(candles),
            first.get("openTime"),
            last.get("openTime"),
            last.get("open"),
            last.get("high"),
            last.get("low"),
            last.get("close"),
        )

    def analyze(self, market_data, strategy="SCALPING"):

        strategy = strategy.upper()

        if strategy not in ["SCALPING", "SWING"]:
            return {
                "decision": "WAIT",
                "reason": "Invalid strategy",
                "execution_authorized": False
            }

        if not isinstance(market_data, dict):
            return {
                "decision": "WAIT",
                "reason": "Invalid market data",
                "execution_authorized": False
            }

        results = {}

        for timeframe in self.TIMEFRAMES:

            data = market_data.get(timeframe)

            if not isinstance(data, dict):
                return {
                    "decision": "WAIT",
                    "reason": timeframe + " data missing",
                    "execution_authorized": False
                }

            if (
                not data.get("success")
                or not data.get("signal_allowed")
                or data.get("status") != "LIVE_DATA_READY"
            ):
                return {
                    "decision": "WAIT",
                    "reason": timeframe + " data is unavailable or stale",
                    "blocked_timeframe": timeframe,
                    "execution_authorized": False
                }

            candles = data.get("candles", [])

            # Cache only higher timeframes.
            # M5 is always recalculated for each new decision.
            if self.cache_enabled and timeframe != "M5":
                cache_key = self._cache_key(candles)
                cached = self._cache.get(timeframe)

                if cached is not None and cached[0] == cache_key:
                    results[timeframe] = cached[1]
                else:
                    result = self.analyzer.analyze(candles)
                    results[timeframe] = result

                    if cache_key is not None:
                        self._cache[timeframe] = (cache_key, result)
            else:
                results[timeframe] = self.analyzer.analyze(candles)

            if results[timeframe].get("decision") == "WAIT":
                if not results[timeframe].get("trend"):
                    return {
                        "decision": "WAIT",
                        "reason": timeframe + " analysis unavailable",
                        "timeframe_results": results,
                        "execution_authorized": False
                    }

        trends = {
            timeframe: results[timeframe].get("trend")
            for timeframe in self.TIMEFRAMES
        }

        higher_trends = [trends["H4"], trends["H1"]]

        if higher_trends[0] != higher_trends[1]:
            return {
                "decision": "WAIT",
                "reason": "H4 and H1 trends disagree",
                "timeframe_trends": trends,
                "timeframe_results": results,
                "execution_authorized": False
            }

        direction = higher_trends[0]

        if direction not in ["BULLISH", "BEARISH"]:
            return {
                "decision": "WAIT",
                "reason": "No clear higher-timeframe trend",
                "timeframe_trends": trends,
                "timeframe_results": results,
                "execution_authorized": False
            }

        expected_signal = (
            "BUY_SETUP" if direction == "BULLISH"
            else "SELL_SETUP"
        )

        if strategy == "SCALPING":

            if trends["M15"] != direction:
                reason = "M15 does not confirm the higher-timeframe trend"

            elif results["M5"].get("decision") != expected_signal:
                reason = "M5 has no matching entry setup"

            else:
                reason = None

        else:

            if trends["M15"] not in [
                direction, "SIDEWAYS_OR_UNCONFIRMED"
            ]:
                reason = "M15 contradicts the swing direction"

            elif trends["M5"] not in [
                direction, "SIDEWAYS_OR_UNCONFIRMED"
            ]:
                reason = "M5 contradicts the swing direction"

            elif results["H1"].get("decision") != expected_signal:
                reason = "H1 has no matching swing setup"

            else:
                reason = None

        if reason:
            return {
                "decision": "WAIT",
                "reason": reason,
                "strategy": strategy,
                "timeframe_trends": trends,
                "timeframe_results": results,
                "execution_authorized": False
            }

        return {
            "decision": expected_signal,
            "reason": "All required timeframe conditions agree",
            "strategy": strategy,
            "timeframe_trends": trends,
            "timeframe_results": results,
            "execution_authorized": False
        }
