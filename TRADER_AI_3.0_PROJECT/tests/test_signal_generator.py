import unittest

from analysis.signal_generator import TradeSignalGenerator


class FakeAnalyzer:
    def __init__(self, decision="BUY_SETUP"):
        self.decision = decision

    def analyze(self, market_data, strategy="SCALPING"):
        if self.decision == "WAIT":
            return {"decision": "WAIT", "reason": "Timeframes do not agree",
                    "timeframe_trends": {"H4": "BULLISH", "H1": "BEARISH"}}
        trend = "BULLISH" if self.decision == "BUY_SETUP" else "BEARISH"
        return {
            "decision": self.decision,
            "reason": "All required timeframe conditions agree",
            "timeframe_trends": {"M5": trend, "M15": trend, "H1": trend, "H4": trend},
            "timeframe_results": {
                "M5": {"atr14": 2.0, "patterns": ["BULLISH_ENGULFING"]},
                "H1": {"atr14": 5.0, "patterns": []},
            },
        }


def candle(open_price, high, low, close, index):
    return {"openTime": f"2026-01-01T00:{index:02d}:00+00:00",
            "open": open_price, "high": high, "low": low, "close": close}


def market_data():
    m5 = [candle(100 + i * .1, 101 + i * .1, 99 + i * .1,
                 100.5 + i * .1, i) for i in range(20)]
    h1 = [candle(100 + i, 105 + i, 95 + i, 102 + i, i)
          for i in range(20)]
    return {
        "M5": {"candles": m5},
        "M15": {"candles": m5},
        "H1": {"candles": h1},
        "H4": {"candles": h1},
    }


class TradeSignalGeneratorTests(unittest.TestCase):
    def test_buy_signal_has_entry_structure_stop_and_two_targets(self):
        generator = TradeSignalGenerator(analyzer=FakeAnalyzer("BUY_SETUP"))
        result = generator.generate(market_data(), equity=250, strategy="SCALPING")
        self.assertEqual(result["status"], "SIGNAL_READY")
        self.assertEqual(result["decision"], "BUY")
        self.assertLess(result["stop_loss"], result["entry"])
        self.assertGreater(result["take_profit_1"], result["entry"])
        self.assertGreater(result["take_profit_2"], result["take_profit_1"])
        self.assertEqual(result["risk"]["risk_budget"], 2.5)
        self.assertIsNone(result["risk"]["lot_size"])
        self.assertFalse(result["execution_authorized"])

    def test_sell_signal_has_targets_below_entry(self):
        generator = TradeSignalGenerator(analyzer=FakeAnalyzer("SELL_SETUP"))
        result = generator.generate(market_data(), equity=100, strategy="SCALPING")
        self.assertEqual(result["decision"], "SELL")
        self.assertGreater(result["stop_loss"], result["entry"])
        self.assertLess(result["take_profit_1"], result["entry"])
        self.assertLess(result["take_profit_2"], result["take_profit_1"])

    def test_wait_is_preserved_when_timeframes_disagree(self):
        generator = TradeSignalGenerator(analyzer=FakeAnalyzer("WAIT"))
        result = generator.generate(market_data(), equity=100)
        self.assertEqual(result["decision"], "WAIT")
        self.assertEqual(result["status"], "NO_TRADE")

    def test_missing_or_invalid_equity_is_rejected(self):
        generator = TradeSignalGenerator(analyzer=FakeAnalyzer("BUY_SETUP"))
        for equity in (None, 0, -1, float("nan"), True):
            with self.subTest(equity=equity):
                self.assertEqual(generator.generate(market_data(), equity=equity)["decision"], "WAIT")

    def test_risk_above_one_percent_is_rejected(self):
        generator = TradeSignalGenerator(analyzer=FakeAnalyzer("BUY_SETUP"))
        result = generator.generate(market_data(), equity=100, risk_percent=2)
        self.assertEqual(result["decision"], "WAIT")

    def test_structure_stop_that_crosses_entry_is_rejected(self):
        data = market_data()
        data["M5"]["candles"][-12:] = [candle(110, 112, 111, 113, i)
                                              for i in range(8, 20)]
        generator = TradeSignalGenerator(analyzer=FakeAnalyzer("BUY_SETUP"))
        result = generator.generate(data, equity=100)
        self.assertEqual(result["decision"], "WAIT")


if __name__ == "__main__":
    unittest.main()
