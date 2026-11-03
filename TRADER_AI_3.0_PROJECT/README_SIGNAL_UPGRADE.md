# TRADER AI 2.0 — Signal generation upgrade

## What this upgrade adds

- A dedicated signal generator that combines the existing M5/M15/H1/H4 rule-based analyzer with a trade-plan builder.
- BUY / SELL / WAIT decisions for the selected SCALPING or SWING strategy.
- Reference entry and entry zone, structure-based stop loss, TP1 at 1R and TP2 at 2R.
- A 1% risk-budget calculation from the equity entered by the user.
- A dashboard action to request a signal and display the plan.
- Fail-closed behaviour: missing, stale or unavailable timeframe data results in WAIT; execution is always disabled.
- No hardcoded account equity in the dashboard status.

## Important limitations

- The current analysis is deterministic, indicator/candlestick rule-based analysis. It is not a trained machine-learning model.
- The current market-data client uses an external XAUUSD feed, not verified HFM/MT5 quotes.
- Entry is a reference based on the last completed M5 candle close. It is not a guaranteed executable price. Check the current HFM quote and spread before considering any trade.
- SL is based on recent market structure with an ATR buffer. TP1 and TP2 are planned at 1R and 2R.
- Lot sizing is intentionally disabled until HFM's XAUUSD contract size, tick value, volume step, account currency conversion, commissions and other execution costs are verified.
- No orders are sent. `execution_authorized` is always `false`.
- Generating a signal is a one-time request, not a continuous background trading loop.
- Historical proxy examples and passing unit tests do not establish profitability. Validate with out-of-sample testing and HFM demo trading.

## Install / run

From the project directory:

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python app.py
```

Open the local dashboard in the phone browser at `http://127.0.0.1:5000` while the app is running.

Enter the current account equity, choose SCALPING or SWING, then tap **GENERATE TRADE SIGNAL**. The server requests M5, M15, H1 and H4 data. A WAIT result is valid and means the filters did not agree or the market data was not suitable.

## API

`POST /signal`

JSON body:

```json
{"equity": 100, "strategy": "SCALPING"}
```

Valid strategies: `SCALPING`, `SWING`. Risk budget is fixed at 1% of supplied equity. The API never authorizes execution.
