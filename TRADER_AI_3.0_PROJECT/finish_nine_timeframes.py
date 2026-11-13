from pathlib import Path
from datetime import datetime
import shutil
import sys

changes = {}

# 1. Flask app
p = Path("app.py")
s = p.read_text(encoding="utf-8")

replacements = [
    (
        "Requesting M5, M15, H1 and H4 market data. This may take a moment.",
        "Requesting all nine market timeframes. This may take a moment."
    ),
    (
        'for timeframe in ("M5", "M15", "H1", "H4"):',
        "for timeframe in MARKET_DATA.TIMEFRAMES:"
    ),
    (
        'timeframe = request.args.get("timeframe", "M5").upper()\n\n    if timeframe not in ["M5", "M15", "H1", "H4"]:',
        'timeframe = request.args.get("timeframe", "M1").upper()\n\n    if timeframe not in MARKET_DATA.TIMEFRAMES:'
    ),
]

for old, new in replacements:
    count = s.count(old)
    if count != 1:
        sys.exit(f"STOP: app.py expected one match, found {count}: {old[:70]!r}")
    s = s.replace(old, new, 1)

changes[p] = s

# 2. Signal generator test fixtures
p = Path("tests/test_signal_generator.py")
s = p.read_text(encoding="utf-8")

replacements = [
    (
        '"timeframe_trends": {"M5": trend, "M15": trend, "H1": trend, "H4": trend},',
        '"timeframe_trends": {tf: trend for tf in ("M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN1")},'
    ),
    (
        '"M5": {"atr14": 2.0, "patterns": ["BULLISH_ENGULFING"]},\n'
        '                "H1": {"atr14": 5.0, "patterns": []},',
        '"M1": {"atr14": 1.0, "patterns": ["BULLISH_ENGULFING"]},\n'
        '                "M5": {"atr14": 2.0, "patterns": []},\n'
        '                "M15": {"atr14": 2.5, "patterns": []},\n'
        '                "H4": {"atr14": 5.0, "patterns": []},'
    ),
    (
        '    return {\n'
        '        "M5": {"candles": m5},\n'
        '        "M15": {"candles": m5},\n'
        '        "H1": {"candles": h1},\n'
        '        "H4": {"candles": h1},\n'
        '    }',
        '    return {\n'
        '        "M1": {"candles": m5},\n'
        '        "M5": {"candles": m5},\n'
        '        "M15": {"candles": m5},\n'
        '        "M30": {"candles": h1},\n'
        '        "H1": {"candles": h1},\n'
        '        "H4": {"candles": h1},\n'
        '        "D1": {"candles": h1},\n'
        '        "W1": {"candles": h1},\n'
        '        "MN1": {"candles": h1},\n'
        '    }'
    ),
]

for old, new in replacements:
    count = s.count(old)
    if count != 1:
        sys.exit(f"STOP: test file expected one match, found {count}: {old[:70]!r}")
    s = s.replace(old, new, 1)

changes[p] = s

# Validate the new test filename before changing any files.
new_test_path = Path("tests/test_multi_timeframe_analyzer.py")
if new_test_path.exists():
    sys.exit(f"STOP: {new_test_path} already exists; refusing to overwrite it.")

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

# All checks passed. Back up current files before writing.
stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup = Path("backups") / f"before_finish_nine_timeframes_{stamp}"
backup.mkdir(parents=True)

for path in changes:
    shutil.copy2(path, backup / path.name)

print("Backup created:", backup)

for path, content in changes.items():
    path.write_text(content, encoding="utf-8")

new_test_path.write_text(new_test, encoding="utf-8")

print("SUCCESS: Flask now requests all nine timeframes.")
print("SUCCESS: /analyze-live accepts all nine timeframes.")
print("SUCCESS: Signal tests now include all nine timeframe fixtures.")
print("SUCCESS: Added focused nine-timeframe analyzer tests.")
