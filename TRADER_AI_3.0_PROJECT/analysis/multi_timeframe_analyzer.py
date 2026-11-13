from analysis.market_analyzer import MarketAnalyzer


class MultiTimeframeAnalyzer:
    TIMEFRAMES = ("M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN1")
    MACRO_TIMEFRAMES = ("D1", "W1", "MN1")
    CONTEXT_TIMEFRAMES = ("H4", "H1")
    SETUP_TIMEFRAMES = ("M30", "M15")
    ENTRY_TIMEFRAMES = ("M5", "M1")

    def __init__(self, cache_enabled=False):
        self.analyzer = MarketAnalyzer()
        self.cache_enabled = cache_enabled
        self._cache = {}

    @staticmethod
    def _cache_key(candles):
        if not candles:
            return None
        first, last = candles[0], candles[-1]
        return (
            len(candles), first.get("openTime"), last.get("openTime"),
            last.get("open"), last.get("high"), last.get("low"),
            last.get("close"),
        )

    @staticmethod
    def _wait(reason, strategy=None, trends=None, results=None, blocked=None):
        response = {
            "decision": "WAIT",
            "reason": reason,
            "execution_authorized": False,
        }
        if strategy:
            response["strategy"] = strategy
        if trends is not None:
            response["timeframe_trends"] = trends
        if results is not None:
            response["timeframe_results"] = results
        if blocked:
            response["blocked_timeframe"] = blocked
        return response

    def analyze(self, market_data, strategy="SCALPING"):
        strategy = str(strategy).upper()
        if strategy not in ("SCALPING", "SWING"):
            return self._wait("Invalid strategy")
        if not isinstance(market_data, dict):
            return self._wait("Invalid market data")

        results = {}
        for timeframe in self.TIMEFRAMES:
            data = market_data.get(timeframe)
            if not isinstance(data, dict):
                return self._wait(
                    timeframe + " data missing", strategy, results=results,
                    blocked=timeframe,
                )
            if (
                not data.get("success")
                or not data.get("signal_allowed")
                or data.get("status") != "LIVE_DATA_READY"
            ):
                return self._wait(
                    timeframe + " data is unavailable or stale",
                    strategy, results=results, blocked=timeframe,
                )

            candles = data.get("candles", [])
            if not isinstance(candles, list) or len(candles) < 60:
                return self._wait(
                    timeframe + " requires at least 60 candles",
                    strategy, results=results, blocked=timeframe,
                )

            cache_key = self._cache_key(candles)
            can_cache = self.cache_enabled and timeframe in self.MACRO_TIMEFRAMES
            cached = self._cache.get(timeframe) if can_cache else None

            if cached is not None and cached[0] == cache_key:
                result = cached[1]
            else:
                result = self.analyzer.analyze(candles)
                if can_cache and cache_key is not None:
                    self._cache[timeframe] = (cache_key, result)

            results[timeframe] = result
            if not isinstance(result, dict) or not result.get("trend"):
                return self._wait(
                    timeframe + " analysis unavailable",
                    strategy, results=results, blocked=timeframe,
                )

        trends = {
            tf: results[tf].get("trend", "SIDEWAYS_OR_UNCONFIRMED")
            for tf in self.TIMEFRAMES
        }

        # At least two of the three macro frames must agree.
        macro = [trends[tf] for tf in self.MACRO_TIMEFRAMES]
        bullish_count = macro.count("BULLISH")
        bearish_count = macro.count("BEARISH")

        if bullish_count >= 2:
            direction = "BULLISH"
        elif bearish_count >= 2:
            direction = "BEARISH"
        else:
            return self._wait(
                "Daily, weekly and monthly trends have no clear majority",
                strategy, trends, results,
            )

        expected = "BUY_SETUP" if direction == "BULLISH" else "SELL_SETUP"
        opposite = "BEARISH" if direction == "BULLISH" else "BULLISH"

        # Higher intraday context may be neutral, but must not oppose the macro.
        for tf in self.CONTEXT_TIMEFRAMES:
            if trends[tf] == opposite:
                return self._wait(
                    tf + " contradicts the macro direction",
                    strategy, trends, results,
                )

        # M30 and M15 must not contradict the macro direction.
        for tf in self.SETUP_TIMEFRAMES:
            if trends[tf] == opposite:
                return self._wait(
                    tf + " contradicts the macro direction",
                    strategy, trends, results,
                )

        if strategy == "SCALPING":
            if trends["M15"] != direction:
                reason = "M15 does not confirm the macro direction"
            elif trends["M5"] == opposite:
                reason = "M5 contradicts the scalping direction"
            elif results["M1"].get("decision") != expected:
                reason = "M1 has no matching entry candle setup"
            else:
                reason = None
        else:
            if trends["H4"] != direction or trends["H1"] != direction:
                reason = "H4 and H1 must confirm the swing direction"
            elif results["M15"].get("decision") != expected:
                reason = "M15 has no matching swing entry setup"
            else:
                reason = None

        if reason:
            return self._wait(reason, strategy, trends, results)

        return {
            "decision": expected,
            "reason": "Nine-timeframe analysis confirms the setup",
            "strategy": strategy,
            "timeframe_trends": trends,
            "timeframe_results": results,
            "execution_authorized": False,
        }
