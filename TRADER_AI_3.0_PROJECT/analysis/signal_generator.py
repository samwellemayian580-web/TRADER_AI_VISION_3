"""Build explicit, non-executable trade plans from validated multi-timeframe data."""

from datetime import datetime, timezone
import math

from analysis.multi_timeframe_analyzer import MultiTimeframeAnalyzer


class TradeSignalGenerator:
    """Convert a confirmed direction into entry, structure SL and R targets.

    Prices are reference levels from completed candles, not broker quotes.
    Broker-specific lot sizing and order execution are intentionally excluded
    until the HFM symbol contract specifications are verified.
    """

    def __init__(self, analyzer=None, structure_lookback=12, stop_buffer_atr=0.15,
                 entry_zone_atr=0.10, target_r_multiples=(1.0, 2.0, 3.0)):
        if not isinstance(structure_lookback, int) or structure_lookback < 3:
            raise ValueError("structure_lookback must be an integer >= 3")
        for name, value in (("stop_buffer_atr", stop_buffer_atr),
                            ("entry_zone_atr", entry_zone_atr)):
            if isinstance(value, bool) or not isinstance(value, (int, float)) \
                    or not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be a finite non-negative number")
        if (not isinstance(target_r_multiples, (tuple, list))
                or len(target_r_multiples) != 3
                or any(isinstance(x, bool) or not isinstance(x, (int, float))
                       or not math.isfinite(x) or x <= 0 for x in target_r_multiples)
                or target_r_multiples[0] >= target_r_multiples[1]):
            raise ValueError("target_r_multiples must contain three increasing positive values")

        self.analyzer = analyzer or MultiTimeframeAnalyzer(cache_enabled=True)
        self.structure_lookback = structure_lookback
        self.stop_buffer_atr = float(stop_buffer_atr)
        self.entry_zone_atr = float(entry_zone_atr)
        self.target_r_multiples = tuple(float(x) for x in target_r_multiples)

    @staticmethod
    def _valid_price(value):
        return (not isinstance(value, bool) and isinstance(value, (int, float))
                and math.isfinite(value) and value > 0)

    @classmethod
    def _valid_candle(cls, candle):
        if not isinstance(candle, dict):
            return False
        values = [candle.get(key) for key in ("open", "high", "low", "close")]
        if not all(cls._valid_price(value) for value in values):
            return False
        open_price, high, low, close = values
        return high >= max(open_price, close) and low <= min(open_price, close) and high >= low

    @staticmethod
    def _wait(reason, **extra):
        return {
            "decision": "WAIT",
            "status": "NO_TRADE",
            "reason": reason,
            "execution_authorized": False,
            **extra,
        }

    def generate(self, market_data, strategy="SCALPING", equity=None,
                 risk_percent=1.0):
        strategy = str(strategy).upper()
        if strategy not in ("SCALPING", "SWING"):
            return self._wait("Strategy must be SCALPING or SWING")
        if (isinstance(equity, bool) or not isinstance(equity, (int, float))
                or not math.isfinite(equity) or equity <= 0):
            return self._wait("Provide a valid account equity to calculate the risk budget")
        if (isinstance(risk_percent, bool) or not isinstance(risk_percent, (int, float))
                or not math.isfinite(risk_percent) or not 0 < risk_percent <= 1.0):
            return self._wait("Signal risk must be greater than 0% and no more than the agreed 1% target")

        analysis = self.analyzer.analyze(market_data, strategy=strategy)
        direction = analysis.get("decision")
        if direction not in ("BUY_SETUP", "SELL_SETUP"):
            return self._wait(
                analysis.get("reason", "No confirmed multi-timeframe setup"),
                strategy=strategy,
                timeframe_trends=analysis.get("timeframe_trends", {}),
                timeframe_results=analysis.get("timeframe_results", {}),
            )

        entry_tf = "M5"
        structure_tf = "M5" if strategy == "SCALPING" else "H1"
        entry_candles = market_data[entry_tf].get("candles", [])
        structure_candles = market_data[structure_tf].get("candles", [])
        if len(entry_candles) < 2 or len(structure_candles) < self.structure_lookback:
            return self._wait("Not enough completed candles to construct a safe trade plan")

        entry = entry_candles[-1].get("close")
        entry_atr = analysis.get("timeframe_results", {}).get(entry_tf, {}).get("atr14")
        structure_atr = analysis.get("timeframe_results", {}).get(structure_tf, {}).get("atr14")
        if not self._valid_price(entry) or not self._valid_price(entry_atr) \
                or not self._valid_price(structure_atr):
            return self._wait("Entry price or ATR data is invalid")

        recent = structure_candles[-self.structure_lookback:]
        if not all(self._valid_candle(candle) for candle in recent):
            return self._wait("Recent market-structure candles contain invalid OHLC values")
        if not all(self._valid_candle(candle) for candle in entry_candles[-2:]):
            return self._wait("Latest entry candles contain invalid OHLC values")
        if direction == "BUY_SETUP":
            swing = min(c.get("low", float("nan")) for c in recent)
            stop = swing - structure_atr * self.stop_buffer_atr
            side = "BUY"
        else:
            swing = max(c.get("high", float("nan")) for c in recent)
            stop = swing + structure_atr * self.stop_buffer_atr
            side = "SELL"

        if not self._valid_price(swing) or not self._valid_price(stop):
            return self._wait("Market structure produced an invalid stop level")
        if (side == "BUY" and stop >= entry) or (side == "SELL" and stop <= entry):
            return self._wait("Market structure stop is on the wrong side of entry; no trade")

        risk_distance = abs(entry - stop)
        if risk_distance < structure_atr * 0.10:
            return self._wait("Stop distance is too small relative to volatility")

        sign = 1.0 if side == "BUY" else -1.0
        tp1 = entry + sign * risk_distance * self.target_r_multiples[0]
        tp2 = entry + sign * risk_distance * self.target_r_multiples[1]
        tp3 = entry + sign * risk_distance * self.target_r_multiples[2]
        zone_half_width = entry_atr * self.entry_zone_atr
        risk_cash = float(equity) * float(risk_percent) / 100.0

        patterns = analysis.get("timeframe_results", {}).get(entry_tf, {}).get("patterns", [])
        source_time = entry_candles[-1].get("openTime")
        return {
            "decision": side,
            "status": "SIGNAL_READY",
            "symbol": "XAUUSD",
            "strategy": strategy,
            "entry": round(float(entry), 3),
            "entry_zone": {
                "low": round(float(entry - zone_half_width), 3),
                "high": round(float(entry + zone_half_width), 3),
            },
            "entry_reference": "Last completed M5 candle close; verify against current broker quote before entry",
            "stop_loss": round(float(stop), 3),
            "take_profit_1": round(float(tp1), 3),
            "take_profit_2": round(float(tp2), 3),
            "take_profit_3": round(float(tp3), 3),
            "risk_distance_price": round(float(risk_distance), 5),
            "targets_r": list(self.target_r_multiples),
            "risk": {
                "risk_percent": float(risk_percent),
                "risk_budget": round(risk_cash, 2),
                "account_equity": round(float(equity), 2),
                "lot_size": None,
                "lot_size_status": "DISABLED_PENDING_HFM_CONTRACT_SPECIFICATION",
            },
            "structure_timeframe": structure_tf,
            "structure_lookback_candles": self.structure_lookback,
            "atr_entry_timeframe": round(float(entry_atr), 5),
            "atr_structure_timeframe": round(float(structure_atr), 5),
            "timeframe_trends": analysis.get("timeframe_trends", {}),
            "patterns": patterns,
            "source_candle_time": source_time,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "execution_authorized": False,
            "warnings": [
                "Reference levels use completed external-feed candles, not verified HFM quotes.",
                "Confirm the current broker price and spread before considering an entry.",
                "Lot sizing and all order execution remain disabled until HFM symbol specifications are verified.",
                "Targets are planned levels, not guaranteed fills or profit forecasts.",
            ],
        }
