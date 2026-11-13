from pathlib import Path
from datetime import datetime
import shutil
import sys

ROOT = Path(".")
FILES = [
    "analysis/multi_timeframe_analyzer.py",
    "analysis/signal_generator.py",
    "app.py",
    "tests/test_signal_generator.py",
]

stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup = Path("backups") / f"before_nine_timeframes_{stamp}"

for name in FILES:
    p = ROOT / name
    if not p.is_file():
        sys.exit(f"STOP: Required file missing: {name}")

backup.mkdir(parents=True)
for name in FILES:
    shutil.copy2(ROOT / name, backup / Path(name).name)

print("Backups created:", backup)

def replace_once(text, old, new, filename):
    count = text.count(old)
    if count != 1:
        sys.exit(
            f"STOP: Expected one matching source section in {filename}; "
            f"found {count}. No source files have been changed."
        )
    return text.replace(old, new, 1)

# 1. Replace the four-timeframe analyzer with a nine-timeframe hierarchy.
analyzer = '''from analysis.market_analyzer import MarketAnalyzer


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
'''

(ROOT / "analysis/multi_timeframe_analyzer.py").write_text(
    analyzer, encoding="utf-8"
)
print("Updated nine-timeframe analyzer.")

# 2. Update signal entry and structure timeframes.
p = ROOT / "analysis/signal_generator.py"
s = p.read_text(encoding="utf-8")
s = replace_once(
    s,
    '        entry_tf = "M5"\\n'
    '        structure_tf = "M5" if strategy == "SCALPING" else "H1"',
    '        entry_tf = "M1" if strategy == "SCALPING" else "M15"\\n'
    '        structure_tf = "M5" if strategy == "SCALPING" else "H4"',
    str(p),
)
s = replace_once(
    s,
    '"entry_reference": "Last completed M5 candle close; verify against current broker quote before entry",',
    '"entry_reference": f"Last completed {entry_tf} candle close; verify against current broker quote before entry",',
    str(p),
)
p.write_text(s, encoding="utf-8")
print("Updated signal entry and structure timeframes.")

# 3. Update Flask signal fetch and live-analysis validation.
p = ROOT / "app.py"
s = p.read_text(encoding="utf-8")
s = replace_once(
    s,
    "Requesting M5, M15, H1 and H4 market data. This may take a moment.",
    "Requesting all nine market timeframes. This may take a moment.",
    str(p),
)
s = replace_once(
    s,
    'for timeframe in ("M5", "M15", "H1", "H4"):',
    "for timeframe in MARKET_DATA.TIMEFRAMES:",
    str(p),
)
s = replace_once(
    s,
    'timeframe = request.args.get("timeframe", "M5").upper()\\n\\n    if timeframe not in ["M5", "M15", "H1", "H4"]:',
    'timeframe = request.args.get("timeframe", "M1").upper()\\n\\n    if timeframe not in MARKET_DATA.TIMEFRAMES:',
    str(p),
)
p.write_text(s, encoding="utf-8")
print("Updated Flask endpoints.")

# 4. Update existing signal tests for the new entry/structure candles.
p = ROOT / "tests/test_signal_generator.py"
s = p.read_text(encoding="utf-8")
s = replace_once(
    s,
    '"timeframe_trends": {"M5": trend, "M15": trend, "H1": trend, "H4": trend},',
    '"timeframe_trends": {tf: trend for tf in ("M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN1")},',
    str(p),
)
s = replace_once(
    s,
    '"M5": {"atr14": 2.0, "patterns": ["BULLISH_ENGULFING"]},\\n'
    '                "H1": {"atr14": 5.0, "patterns": []},',
    '"M1": {"atr14": 1.0, "patterns": ["BULLISH_ENGULFING"]},\\n'
    '                "M5": {"atr14": 2.0, "patterns": []},\\n'
    '                "M15": {"atr14": 2.5, "patterns": []},\\n'
    '                "H4": {"atr14": 5.0, "patterns": []},',
    str(p),
)
s = replace_once(
    s,
    'return {\\n        "M5": {"candles": m5},\\n'
    '        "M15": {"candles": m5},\\n'
    '        "H1": {"candles": h1},\\n'
    '        "H4": {"candles": h1},\\n'
    '    }',
    'return {\\n'
    '        "M1": {"candles": m5},\\n'
    '        "M5": {"candles": m5},\\n'
    '        "M15": {"candles": m5},\\n'
    '        "M30": {"candles": h1},\\n'
    '        "H1": {"candles": h1},\\n'
    '        "H4": {"candles": h1},\\n'
    '        "D1": {"candles": h1},\\n'
    '        "W1": {"candles": h1},\\n'
    '        "MN1": {"candles": h1},\\n'
    '    }',
    str(p),
)
s = replace_once(
    s,
    'data["M5"]["candles"][-12:] = [',
    'data["M5"]["candles"][-12:] = [',
    str(p),
)
p.write_text(s, encoding="utf-8")
print("Updated signal-generator tests.")

# 5. Add focused tests for nine-frame analysis and macro agreement.
new_test = '''import unittest

from analysis.multi_timeframe_analyzer import MultiTimeframeAnalyzer


FRAMES = ("M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN1")


class FakeMarketAnalyzer:
    def analyze(self, candles):
        return candles[0]


def frame(trend="BULLISH", decision="WAIT"):
    candles = [{"trend": trend, "decision": decision} for _ in range(60)]
    return {
        "success": True,
        "signal_allowed": True,
        "status": "LIVE_DATA_READY",
        "candles": candles,
    }


def data_for(direction="BULLISH", strategy="SCALPING"):
    setup = "BUY_SETUP" if direction == "BULLISH" else "SELL_SETUP"
    data = {}
    for tf in FRAMES:
        decision = "WAIT"
        if strategy == "SCALPING" and tf == "M1":
            decision = setup
        if strategy == "SWING" and tf == "M15":
            decision = setup
        data[tf] = frame(direction, decision)
    return data


class NineTimeframeAnalyzerTests(unittest.TestCase):
    def setUp(self):
        self.analyzer = MultiTimeframeAnalyzer()
        self.analyzer.analyzer = FakeMarketAnalyzer()

    def test_all_nine_timeframes_are_analyzed_for_scalping(self):
        result = self.analyzer.analyze(data_for(), "SCALPING")
        self.assertEqual(result["decision"], "BUY_SETUP")
        self.assertEqual(set(result["timeframe_trends"]), set(FRAMES))
        self.assertFalse(result["execution_authorized"])

    def test_all_nine_timeframes_are_analyzed_for_swing(self):
        result = self.analyzer.analyze(data_for(strategy="SWING"), "SWING")
        self.assertEqual(result["decision"], "BUY_SETUP")
        self.assertEqual(set(result["timeframe_trends"]), set(FRAMES))

    def test_missing_timeframe_blocks_signal(self):
        data = data_for()
        del data["MN1"]
        result = self.analyzer.analyze(data)
        self.assertEqual(result["decision"], "WAIT")
        self.assertEqual(result["blocked_timeframe"], "MN1")

    def test_macro_frames_need_two_to_agree(self):
        data = data_for()
        data["D1"] = frame("BEARISH")
        data["W1"] = frame("BEARISH")
        result = self.analyzer.analyze(data)
        self.assertEqual(result["decision"], "WAIT")

    def test_opposing_intraday_context_blocks_signal(self):
        data = data_for()
        data["H4"] = frame("BEARISH")
        result = self.analyzer.analyze(data)
        self.assertEqual(result["decision"], "WAIT")


if __name__ == "__main__":
    unittest.main()
'''

(ROOT / "tests/test_multi_timeframe_analyzer.py").write_text(
    new_test, encoding="utf-8"
)
print("Added nine-timeframe analyzer tests.")
print("Patch complete.")
