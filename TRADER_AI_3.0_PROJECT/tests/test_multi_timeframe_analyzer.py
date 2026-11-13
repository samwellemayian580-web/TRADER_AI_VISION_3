import unittest

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
