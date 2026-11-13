
import os
from flask import Flask, request, jsonify, render_template_string
import math
from analysis.market_analyzer import MarketAnalyzer
from analysis.signal_generator import TradeSignalGenerator
from data.market_data import MarketDataClient
from broker.paper_broker import PaperBroker
from broker.mt5_bridge_client import MT5BridgeClient, BridgeError

app = Flask(__name__)
ANALYZER = MarketAnalyzer()
SIGNAL_GENERATOR = TradeSignalGenerator()
MARKET_DATA = MarketDataClient()
PAPER_BROKER = PaperBroker(starting_equity=1000.0)
MT5_BRIDGE = MT5BridgeClient()

BOT = {
    "name": "TRADER AI 3.0",
    "symbol": "XAUUSD",
    "status": "STOPPED",
    "mode": "SIGNAL_ONLY",
    "execution": "MANUAL",
    "strategy": "SCALPING",
    "risk": 1.0,
    "decision": "WAITING FOR MARKET DATA"
}

PAGE = """
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TRADER AI 3.0</title>
<style>
body {
    background:#10151d; color:white; font-family:Arial;
    max-width:500px; margin:auto; padding:20px;
}
h1 {color:#e8b84b;}
.card {
    background:#1c2633; padding:18px;
    border-radius:12px; margin:15px 0;
}
button,select {
    width:100%; padding:14px; margin-top:10px;
    border:0; border-radius:8px; font-size:16px;
}
.start {background:#168b5a;color:white;}
.stop {background:#b83b45;color:white;}
small {color:#aab6c5;}
</style>
</head>
<body>

<h1>TRADER AI 3.0</h1>
<small>XAUUSD MARKET INTELLIGENCE</small>

<div class="card">
<h3>System status</h3>
<h2 id="status">STOPPED</h2>
<p>Instrument: XAUUSD</p>
<p>Mode: SIGNAL GENERATION ONLY — no broker orders</p>
<p>Risk per trade: <span id="risk">1</span>%</p>
</div>

<div class="card">
<h3>Trading strategy</h3>
<select id="strategy">
<option value="SCALPING">Scalping</option>
<option value="SWING">12–24 Hour Analysis</option>
</select>

<h3>Execution mode</h3>
<select id="execution">
<option value="MANUAL">Manual signal review — no automatic orders</option>
</select>

<button onclick="saveSettings()">SAVE SETTINGS</button>
</div>

<div class="card">
<button class="start" onclick="generateSignal()">GENERATE TRADE SIGNAL</button>
<button class="stop" onclick="stopBot()">STOP / CLEAR STATUS</button>
</div>

<div class="card">
<h3>Signal account settings</h3>
<label for="equity">Account equity (account currency)</label>
<input id="equity" type="number" min="0.01" step="0.01" placeholder="Enter your current balance" style="width:100%;box-sizing:border-box;padding:12px;margin-top:8px;border-radius:8px;border:0">
<p><small>Risk budget is calculated at 1%. Lot sizing remains disabled until HFM contract specifications are verified. Current candles are from an external XAUUSD feed, not confirmed HFM quotes.</small></p>
</div>

<div class="card">
<h3>Market intelligence</h3>
<h2 id="decision">WAITING</h2>
<p id="message">No signal requested yet.</p>
<div id="signalDetails"></div>
</div>

<div class="card">
<h3>System information</h3>
<p>Trading instrument: Gold / USD</p>
<p>Maximum planned risk per trade: 1%</p>
<p>Normal risk target: <span id="normalRisk">1</span>%</p>
<p>Hard per-trade risk ceiling: <span id="maxTradeRisk">10</span>%</p>
<p>Combined risk ceiling: <span id="maxTotalRisk">10</span>%</p>
<p>Broker positions: Not connected / not tracked</p>
<p>HFM lot sizing: Disabled pending broker specifications</p>
</div>

<script>
async function refresh() {
    const response = await fetch('/status');
    const data = await response.json();

    document.getElementById('status').innerText = data.status;
    document.getElementById('strategy').value = data.strategy;
    document.getElementById('execution').value = data.execution;
    document.getElementById('risk').innerText = data.risk;
    document.getElementById('decision').innerText = data.decision;

const risk = data.risk_controls;
document.getElementById('normalRisk').innerText = risk.normal_target_percent;
document.getElementById('maxTradeRisk').innerText = risk.max_risk_per_trade_percent;
document.getElementById('maxTotalRisk').innerText = risk.max_total_risk_percent;
}

async function stopBot() {
    await fetch('/stop', {method:'POST'});
    refresh();
}

async function saveSettings() {
    try {
        const response = await fetch('/settings', {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify({
                strategy:document.getElementById('strategy').value,
                execution:document.getElementById('execution').value
            })
        });
        if (!response.ok) throw new Error('Could not save settings.');
        await refresh();
        document.getElementById('message').innerText = 'Settings saved. No broker orders can be placed.';
    } catch (error) {
        document.getElementById('message').innerText = 'Settings error: ' + error.message;
    }
}

function showSignal(data) {
    const decision = data.decision || 'WAIT';
    document.getElementById('decision').innerText = decision;
    const lines = [];
    lines.push(data.reason || (decision === 'WAIT' ? 'No valid setup at this time.' : 'Signal plan generated.'));
    if (data.status) lines.push('Status: ' + data.status);
    if (data.entry !== undefined) lines.push('Entry reference: ' + data.entry);
    if (data.entry_zone) lines.push('Entry zone: ' + data.entry_zone.low + ' – ' + data.entry_zone.high);
    if (data.stop_loss !== undefined) lines.push('Stop loss: ' + data.stop_loss);
    if (data.take_profit_1 !== undefined) lines.push('Take profit 1: ' + data.take_profit_1);
    if (data.take_profit_2 !== undefined) lines.push('Take profit 2: ' + data.take_profit_2);
    if (data.risk) lines.push('Risk budget: ' + data.risk.risk_budget + ' (' + data.risk.risk_percent + '%)');
    if (data.timeframe_status) lines.push('Timeframes: ' + Object.entries(data.timeframe_status).map(([tf, status]) => tf + '=' + status).join(', '));
    if (data.warnings && data.warnings.length) lines.push('Warnings: ' + data.warnings.join(' '));
    lines.push('Broker execution: DISABLED');
    document.getElementById('message').innerText = lines.join('\\n\\n');
}

async function generateSignal() {
    const button = document.querySelector('.start');
    const equityInput = document.getElementById('equity');
    const equity = Number(equityInput.value);
    if (!equityInput.value || !Number.isFinite(equity) || equity <= 0) {
        document.getElementById('decision').innerText = 'WAIT';
        document.getElementById('message').innerText = 'Enter a valid account equity first, then tap GENERATE TRADE SIGNAL.';
        equityInput.focus();
        return;
    }

    button.disabled = true;
    button.innerText = 'ANALYSING MARKET...';
    document.getElementById('decision').innerText = 'ANALYSING';
    document.getElementById('message').innerText = 'Requesting all nine market timeframes. This may take a moment.';
    try {
        const response = await fetch('/signal', {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify({
                equity: equity,
                strategy: document.getElementById('strategy').value
            })
        });
        const data = await response.json();
        showSignal(data);
        if (!response.ok) {
            document.getElementById('message').innerText = (data.reason || 'Signal request failed.') +
                (data.timeframe_status ? '\\n\\nTimeframes: ' + JSON.stringify(data.timeframe_status) : '');
        }
        await refresh();
    } catch (error) {
        document.getElementById('decision').innerText = 'DATA ERROR';
        document.getElementById('message').innerText = 'Could not complete the signal request: ' + error.message +
            '\\n\\nCheck that Termux is still running and that the market-data connection is available.';
    } finally {
        button.disabled = false;
        button.innerText = 'GENERATE TRADE SIGNAL';
    }
}

refresh();
</script>
</body>
</html>
"""

@app.route("/")
def home():
    return render_template_string(PAGE)

@app.route("/status")
def status():
    response = dict(BOT)
    response["risk_controls"] = {
        "equity": None,
        "normal_target_percent": 1.0,
        "max_risk_per_trade_percent": 10.0,
        "max_total_risk_percent": 10.0,
        "max_positions": 5,
        "open_positions": 0,
        "current_open_risk": 0.0,
        "remaining_risk": None,
        "equity_source": "Not connected; provide current equity when requesting a signal",
    }
    return jsonify(response)

@app.route("/start", methods=["POST"])
def start():
    BOT["status"] = "ANALYSIS RUNNING"
    return jsonify(BOT)

@app.route("/stop", methods=["POST"])
def stop():
    BOT["status"] = "STOPPED"
    return jsonify(BOT)

@app.route("/settings", methods=["POST"])
def settings():
    data = request.get_json() or {}

    if data.get("strategy") in ["SCALPING", "SWING"]:
        BOT["strategy"] = data["strategy"]

    if data.get("execution") == "MANUAL":
        BOT["execution"] = "MANUAL"

    return jsonify(BOT)



@app.route("/analyze", methods=["POST"])
def analyze_market():
    data = request.get_json(silent=True) or {}
    candles = data.get("candles")

    if not isinstance(candles, list):
        return jsonify({
            "decision": "WAIT",
            "reason": "Send candle data as a list"
        }), 400

    result = ANALYZER.analyze(candles)
    BOT["decision"] = result["decision"]

    return jsonify(result)



@app.route("/market-data")
def market_data():
    timeframe = request.args.get("timeframe", "M5").upper()

    if timeframe not in MARKET_DATA.TIMEFRAMES:
        return jsonify({
            "success": False,
            "status": "INVALID_TIMEFRAME",
            "message": "Use M1, M5, M15, M30, H1, H4, D1, W1 or MN1"
        }), 400

    result = MARKET_DATA.fetch(timeframe, 100)
    return jsonify(result)


@app.route("/signal", methods=["POST"])
def generate_signal():
    data = request.get_json(silent=True) or {}
    strategy = data.get("strategy", BOT.get("strategy", "SCALPING"))
    equity = data.get("equity")
    if (isinstance(equity, bool) or not isinstance(equity, (int, float))
            or not math.isfinite(equity) or equity <= 0):
        return jsonify({
            "decision": "WAIT",
            "status": "INVALID_ACCOUNT_EQUITY",
            "reason": "Enter a valid account equity before requesting a signal",
            "execution_authorized": False,
        }), 400
    if strategy not in ("SCALPING", "SWING"):
        return jsonify({
            "decision": "WAIT",
            "status": "INVALID_STRATEGY",
            "reason": "Strategy must be SCALPING or SWING",
            "execution_authorized": False,
        }), 400

    market_data = {}
    timeframe_status = {}
    for timeframe in MARKET_DATA.TIMEFRAMES:
        result = MARKET_DATA.fetch(timeframe, 100)
        market_data[timeframe] = result
        timeframe_status[timeframe] = result.get("status", "DATA_ERROR")
        if not result.get("success"):
            return jsonify({
                "decision": "WAIT",
                "status": "MARKET_DATA_UNAVAILABLE",
                "reason": f"{timeframe} market data could not be loaded",
                "timeframe_status": timeframe_status,
                "execution_authorized": False,
            }), 503

    result = SIGNAL_GENERATOR.generate(
        market_data,
        strategy=strategy,
        equity=equity,
        risk_percent=1.0,
    )
    result["timeframe_status"] = timeframe_status
    result["execution_authorized"] = False
    BOT["decision"] = result.get("decision", "WAIT")
    return jsonify(result)


@app.route("/analyze-live", methods=["GET"])
def analyze_live():
    strategy = request.args.get(
        "strategy", BOT.get("strategy", "SCALPING")
    ).upper()

    if strategy not in ("SCALPING", "SWING"):
        return jsonify({
            "decision": "WAIT",
            "status": "INVALID_STRATEGY",
            "reason": "Strategy must be SCALPING or SWING",
            "execution_authorized": False,
        }), 400

    market_data = {}
    timeframe_status = {}

    for timeframe in MARKET_DATA.TIMEFRAMES:
        market = MARKET_DATA.fetch(timeframe, 100)
        market_data[timeframe] = market
        timeframe_status[timeframe] = market.get(
            "status", "DATA_ERROR"
        )

    result = SIGNAL_GENERATOR.analyzer.analyze(
        market_data, strategy=strategy
    )

    BOT["decision"] = result.get("decision", "WAIT")

    result["symbol"] = "XAUUSD"
    result["strategy"] = strategy
    result["timeframe_status"] = timeframe_status
    result["analysis_source"] = (
        "Twelve Data REST candles; not verified HFM broker quotes"
    )
    result["execution_authorized"] = False
    result["status"] = (
        "NO_TRADE"
        if result.get("decision") == "WAIT"
        else "ANALYSIS_READY"
    )

    return jsonify(result)


# PAPER BROKER API
# Simulation only. These endpoints never contact HFM or MT5.

def paper_local_only():
    return request.remote_addr in ("127.0.0.1", "::1")


@app.route("/paper/status", methods=["GET"])
def paper_status():
    if not paper_local_only():
        return jsonify({"success": False, "reason": "Local access only"}), 403

    return jsonify({
        "success": True,
        "account": PAPER_BROKER.get_account()
    })


@app.route("/paper/positions", methods=["GET"])
def paper_positions():
    if not paper_local_only():
        return jsonify({"success": False, "reason": "Local access only"}), 403

    return jsonify({
        "success": True,
        "mode": "PAPER",
        "live_trading": False,
        "positions": PAPER_BROKER.get_positions()
    })


@app.route("/paper/order", methods=["POST"])
def paper_order():
    if not paper_local_only():
        return jsonify({"success": False, "reason": "Local access only"}), 403

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"success": False, "reason": "Send a JSON object"}), 400

    required = (
        "symbol", "side", "volume",
        "entry_price", "stop_loss", "take_profit"
    )
    missing = [key for key in required if key not in data]

    if missing:
        return jsonify({
            "success": False,
            "reason": "Missing required fields",
            "missing": missing
        }), 400

    try:
        result = PAPER_BROKER.place_order(
            symbol=data["symbol"],
            side=data["side"],
            volume=data["volume"],
            entry_price=data["entry_price"],
            stop_loss=data["stop_loss"],
            take_profit=data["take_profit"],
        )
        return jsonify(result), 201

    except (ValueError, TypeError) as exc:
        return jsonify({
            "success": False,
            "mode": "PAPER",
            "live_trading": False,
            "reason": str(exc)
        }), 400


@app.route("/paper/close", methods=["POST"])
def paper_close():
    if not paper_local_only():
        return jsonify({"success": False, "reason": "Local access only"}), 403

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"success": False, "reason": "Send a JSON object"}), 400

    if "ticket" not in data or "exit_price" not in data:
        return jsonify({
            "success": False,
            "reason": "ticket and exit_price are required"
        }), 400

    try:
        result = PAPER_BROKER.close_position(
            ticket=data["ticket"],
            exit_price=data["exit_price"]
        )
        return jsonify(result)

    except (ValueError, TypeError) as exc:
        return jsonify({
            "success": False,
            "mode": "PAPER",
            "live_trading": False,
            "reason": str(exc)
        }), 400




def vps_local_only():
    return request.remote_addr in ("127.0.0.1", "::1")


@app.route("/vps/status", methods=["GET"])
def vps_status():
    if not vps_local_only():
        return jsonify({"success": False, "error": "Local access only."}), 403

    result = MT5_BRIDGE.check_connection()
    return jsonify(result), (200 if result["connected"] else 503)


@app.route("/vps/account", methods=["GET"])
def vps_account():
    if not vps_local_only():
        return jsonify({"success": False, "error": "Local access only."}), 403

    try:
        return jsonify({
            "success": True,
            "data": MT5_BRIDGE.get_account()
        })
    except BridgeError as exc:
        return jsonify({"success": False, "error": str(exc)}), 503



@app.route("/vps/order", methods=["POST"])
def vps_order():
    if not vps_local_only():
        return jsonify({"success": False, "error": "Local access only."}), 403

    body = request.get_json(silent=True)
    required = {
        "request_id", "symbol", "side",
        "volume", "stop_loss", "take_profit"
    }
    if not isinstance(body, dict) or set(body) != required:
        return jsonify({
            "success": False,
            "error": "Invalid order request fields."
        }), 400

    try:
        result = MT5_BRIDGE.place_order(body)
        return jsonify(result)
    except BridgeError as exc:
        return jsonify({
            "success": False,
            "error": str(exc)
        }), 503


@app.route("/vps/batch", methods=["POST"])
def vps_batch():
    if not vps_local_only():
        return jsonify({"success": False, "error": "Local access only."}), 403

    body = request.get_json(silent=True)
    required = {"setup_id", "batch", "take_profit"}
    if not isinstance(body, dict) or set(body) != required:
        return jsonify({
            "success": False,
            "error": "Invalid batch request fields."
        }), 400

    setup_id = body.get("setup_id")
    batch = body.get("batch")
    take_profit = body.get("take_profit")

    if not isinstance(setup_id, str) or not setup_id.strip():
        return jsonify({"success": False, "error": "A valid setup_id is required."}), 400
    if not isinstance(batch, dict) or batch.get("approved") is not True:
        return jsonify({"success": False, "error": "Only an approved batch can be submitted."}), 400
    if batch.get("side") not in ("BUY", "SELL"):
        return jsonify({"success": False, "error": "Invalid batch side."}), 400
    if not isinstance(batch.get("orders"), list) or not batch["orders"]:
        return jsonify({"success": False, "error": "Batch must contain child orders."}), 400

    try:
        result = MT5_BRIDGE.place_batch(setup_id, batch, take_profit)
        return jsonify(result)
    except BridgeError as exc:
        return jsonify({"success": False, "error": str(exc)}), 503


@app.route("/vps/positions", methods=["GET"])
def vps_positions():
    if not vps_local_only():
        return jsonify({"success": False, "error": "Local access only."}), 403

    try:
        return jsonify({
            "success": True,
            "data": MT5_BRIDGE.get_positions("XAUUSD")
        })
    except BridgeError as exc:
        return jsonify({"success": False, "error": str(exc)}), 503


@app.route("/vps/quote", methods=["GET"])
def vps_quote():
    if not vps_local_only():
        return jsonify({"success": False, "error": "Local access only."}), 403

    symbol = request.args.get("symbol", "XAUUSD")

    if symbol != "XAUUSD":
        return jsonify({
            "success": False,
            "error": "Only XAUUSD is enabled."
        }), 400

    try:
        return jsonify({
            "success": True,
            "data": MT5_BRIDGE.get_quote(symbol)
        })
    except BridgeError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
