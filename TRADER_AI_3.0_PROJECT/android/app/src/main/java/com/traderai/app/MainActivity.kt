import com.chaquo.python.Pythonpackage com.traderai.app

import android.app.Activity
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.graphics.*
import android.graphics.drawable.GradientDrawable
import android.view.Gravity
import android.view.View
import android.widget.*
import android.text.InputType
import org.json.JSONObject
import org.json.JSONArray
import java.net.HttpURLConnection
import java.net.URL
import java.io.IOException
import java.util.concurrent.Executors
import java.text.SimpleDateFormat
import java.util.Locale

class MainActivity : Activity() {
    // Backend is currently expected to run locally on the same Android device (for example in Termux).
    private val baseUrl = "http://127.0.0.1:5000"
    private val executor = Executors.newSingleThreadExecutor()
    private lateinit var root: LinearLayout
    private lateinit var content: LinearLayout
    private lateinit var nav: LinearLayout
    private lateinit var statusView: TextView
    private lateinit var decisionView: TextView
    private lateinit var messageView: TextView
    private lateinit var detailsView: TextView
    private lateinit var equityInput: EditText
    private lateinit var strategySpinner: Spinner
    private lateinit var chartView: CandleChartView
    private lateinit var chartStatus: TextView
    private var selectedPage = "HOME"
    private var selectedTimeframe = "M5"
    private val chartRefreshHandler = Handler(Looper.getMainLooper())
    private val chartRefreshIntervalMs = 120_000L
    private val chartRefreshTask = object : Runnable {
        override fun run() {
            if (selectedPage == "CHART") {
                loadCandles()
                chartRefreshHandler.postDelayed(this, chartRefreshIntervalMs)
            }
        }
    }
    private var latestCandles = mutableListOf<Candle>()
    private val gold = Color.rgb(239, 194, 74)
    private val purple = Color.rgb(155, 83, 255)
    private val teal = Color.rgb(49, 220, 190)
    private val white = Color.WHITE
    private val muted = Color.rgb(169, 171, 205)
    private val cardColor = Color.rgb(20, 22, 43)

    override fun onCreate(savedInstanceState: Bundle?) {
    super.onCreate(savedInstanceState)
    buildShell("HOME")

    executor.execute {
        try {
            Python.getInstance()
                .getModule("android_server")
                .callAttr("start_server")

            runOnUiThread {
                refreshStatus()
            }
        } catch (e: Exception) {
            runOnUiThread {
                statusView.text = "PYTHON ENGINE ERROR: ${e.message}"
            }
        }
    }
}
    }

    private fun buildShell(pageName: String) {
        selectedPage = pageName
        root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(16), dp(18), dp(16), dp(8))
            background = GradientDrawable(GradientDrawable.Orientation.TL_BR,
                intArrayOf(Color.rgb(32, 13, 67), Color.rgb(13, 18, 48), Color.rgb(5, 23, 38)))
        }
        val header = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        header.addView(uiText("♛  TRADER AI 3.0", 23f, gold, true))
        header.addView(uiText("MIDNIGHT AURORA  •  GOLD LIVE CHART", 10f, muted, true))
        root.addView(header)
        val divider = View(this).apply { setBackgroundColor(Color.argb(90, 139, 104, 255)) }
        root.addView(divider, LinearLayout.LayoutParams(-1, dp(1)).apply { topMargin = dp(10); bottomMargin = dp(10) })
        content = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        val scroll = ScrollView(this)
        scroll.addView(content)
        root.addView(scroll, LinearLayout.LayoutParams(-1, 0, 1f))
        nav = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
            setPadding(0, dp(8), 0, dp(3))
            background = rounded(Color.rgb(12, 14, 33), Color.rgb(87, 54, 150), 18)
        }
        listOf("HOME", "CHART", "AI", "TRADES", "SETTINGS").forEach { name ->
            val label = when(name) { "CHART" -> "Charts"; "AI" -> "AI"; else -> name.lowercase().replaceFirstChar { it.uppercase() } }
            val b = TextView(this).apply {
                text = (if (selectedPage == name) "◆\n" else "◇\n") + label
                textSize = 11f
                gravity = Gravity.CENTER
                setTextColor(if (selectedPage == name) gold else muted)
                setPadding(dp(7), dp(5), dp(7), dp(5))
                setOnClickListener { showPage(name) }
            }
            nav.addView(b, LinearLayout.LayoutParams(0, -2, 1f))
        }
        root.addView(nav)
        setContentView(root)
        renderPage(pageName)
    }

    private fun showPage(name: String) {
        chartRefreshHandler.removeCallbacks(chartRefreshTask)
        buildShell(name)
        if (name == "CHART") chartRefreshHandler.postDelayed(chartRefreshTask, chartRefreshIntervalMs)
    }

    private fun renderPage(page: String) {
        content.removeAllViews()
        when(page) {
            "HOME" -> homePage()
            "CHART" -> chartPage()
            "AI" -> aiPage()
            "TRADES" -> tradesPage()
            "SETTINGS" -> settingsPage()
            "RISK" -> riskPage()
        }
    }

    private fun homePage() {
        content.addView(uiText("COMMAND CENTRE", 18f, white, true))
        val hero = card()
        hero.addView(uiText("XAUUSD  •  GOLD SPOT", 12f, muted, true))
        hero.addView(uiText("Live market overview", 22f, gold, true))
        hero.addView(uiText("Feed and account status appear here when connected.", 12f, muted))
        hero.addView(uiText("●  ENGINE STATUS", 12f, teal, true))
        statusView = uiText("Checking engine…", 14f, white)
        hero.addView(statusView)
        content.addView(hero)
        val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        row.addView(metricCard("DAILY P/L", "—", teal), LinearLayout.LayoutParams(0, -2, 1f))
        row.addView(metricCard("OPEN SETUPS", "0", gold), LinearLayout.LayoutParams(0, -2, 1f).apply { leftMargin = dp(8) })
        content.addView(row)
        val controls = card()
        controls.addView(uiText("AUTOMATION CONTROL", 14f, white, true))
        controls.addView(uiText("Starting authorizes entries only within configured safeguards. Stop prevents new automated entries; it does not silently close open trades.", 11f, muted))
        button(controls, "START TRADING", purple) { startBot() }
        button(controls, "STOP TRADING", Color.rgb(170, 54, 79)) { stopBot() }
        content.addView(controls)
        val quick = card()
        quick.addView(uiText("QUICK ACCESS", 14f, white, true))
        button(quick, "Open Golden Live Chart", gold) { showPage("CHART") }
        button(quick, "AI Intelligence", purple) { showPage("AI") }
        button(quick, "Risk Management", Color.rgb(45, 89, 132)) { showPage("RISK") }
        content.addView(quick)
        val info = card()
        info.addView(uiText("SYSTEM SAFETY", 13f, gold, true))
        info.addView(uiText("Broker execution is currently disabled in this project. This screen does not place HFM orders.", 12f, muted))
        content.addView(info)
    }

    private fun chartPage() {
        content.addView(uiText("LIVE GOLD CHART", 18f, white, true))
        val marketCard = card(Color.rgb(48, 35, 8), Color.rgb(255, 207, 74))
        marketCard.addView(uiText("XAUUSD  /  GOLD SPOT", 12f, gold, true))
        marketCard.addView(uiText("GOLDEN LIVE MARKET", 22f, Color.rgb(255, 224, 139), true))
        chartStatus = uiText("Waiting for live candle feed…", 11f, muted)
        marketCard.addView(chartStatus)
        val tfScroll = HorizontalScrollView(this).apply { isHorizontalScrollBarEnabled = false }
        val tfRow = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
        listOf("1m" to "M1", "5m" to "M5", "15m" to "M15", "30m" to "M30", "1H" to "H1", "4H" to "H4", "1D" to "D1", "1W" to "W1", "1M" to "MN1").forEach { (tf, backendTf) ->
            val b = TextView(this).apply {
                text = tf
                gravity = Gravity.CENTER
                textSize = 11f
                setTextColor(if (backendTf == selectedTimeframe) Color.BLACK else if (backendTf.isEmpty()) Color.GRAY else gold)
                background = rounded(if (backendTf == selectedTimeframe) gold else Color.rgb(47, 39, 23), Color.rgb(125, 94, 38), 8)
                setPadding(dp(10), dp(8), dp(10), dp(8))
                alpha = if (backendTf.isEmpty()) .45f else 1f
                setOnClickListener {
                    selectedTimeframe = backendTf
                    loadCandles()
                }
            }
            tfRow.addView(b, LinearLayout.LayoutParams(-2, -2).apply { rightMargin = dp(5) })
        }
        tfScroll.addView(tfRow)
        marketCard.addView(tfScroll)
        chartView = CandleChartView(this)
        marketCard.addView(chartView, LinearLayout.LayoutParams(-1, dp(300)).apply { topMargin = dp(8) })
        marketCard.addView(uiText("ENTRY  ─ ─ ─     TAKE PROFIT  ─ ─ ─     STOP LOSS  ─ ─ ─", 9f, gold))
        marketCard.addView(uiText("Chart uses returned XAUUSD candles. If the feed fails or is stale, it will show a warning instead of pretending prices are live.", 10f, muted))
        content.addView(marketCard)
        button(content, "REFRESH GOLD CANDLES", gold) { loadCandles() }
        button(content, "Open AI Market Analysis", purple) { showPage("AI") }
        loadCandles()
    }

    private fun aiPage() {
        content.addView(uiText("AI INTELLIGENCE", 18f, white, true))
        val c = card()
        c.addView(uiText("MARKET STRUCTURE", 12f, muted, true))
        c.addView(uiText("XAUUSD analysis", 21f, purple, true))
        c.addView(uiText("Trend, support/resistance, candle patterns and multi-timeframe confirmation are requested from the current analysis engine.", 12f, muted))
        content.addView(c)
        val signal = card()
        signal.addView(uiText("GENERATE MARKET SIGNAL", 14f, white, true))
        strategySpinner = Spinner(this)
        strategySpinner.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, listOf("SCALPING", "SWING"))
        signal.addView(strategySpinner)
        equityInput = EditText(this).apply {
            hint = "Account equity (any valid balance)"
            inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL
            setSingleLine(true); setTextColor(white); setHintTextColor(muted)
            background = rounded(Color.rgb(25, 28, 48), Color.rgb(83, 73, 126), 10)
            setPadding(dp(12), dp(10), dp(12), dp(10))
        }
        signal.addView(equityInput)
        button(signal, "ANALYZE XAUUSD", purple) { generateSignal() }
        decisionView = uiText("WAITING", 22f, gold, true)
        messageView = uiText("No analysis requested yet.", 12f, muted)
        detailsView = uiText("", 11f, muted)
        signal.addView(decisionView); signal.addView(messageView); signal.addView(detailsView)
        content.addView(signal)
        button(content, "Refresh engine status", Color.rgb(47, 39, 74)) { refreshStatus() }
    }

    private fun tradesPage() {
        content.addView(uiText("TRADE CENTRE", 18f, white, true))
        val c = card()
        c.addView(uiText("OPEN POSITIONS", 14f, white, true))
        c.addView(uiText("No broker positions are connected yet.", 13f, muted))
        c.addView(uiText("HFM MT5 execution is not integrated or enabled in this build.", 11f, gold))
        content.addView(c)
        val hist = card()
        hist.addView(uiText("TRADE HISTORY", 14f, white, true))
        hist.addView(uiText("History will populate after a verified broker connection is implemented. Signal previews are not actual trades.", 12f, muted))
        content.addView(hist)
    }

    private fun settingsPage() {
        content.addView(uiText("SETTINGS", 18f, white, true))
        val c = card()
        c.addView(uiText("TRADER AI 3.0  •  NEW APP BUILD", 16f, gold, true))
        c.addView(uiText("Theme: Midnight Aurora\nInstrument: XAUUSD\nMarket data: external Gold Spot feed\nBroker: HFM MT5 — not connected", 12f, muted))
        button(c, "RISK MANAGEMENT", Color.rgb(46, 81, 130)) { showPage("RISK") }
        button(c, "CONNECTION STATUS", purple) { refreshStatus() }
        content.addView(c)
        val safe = card()
        safe.addView(uiText("CONNECTION CONFIGURATION", 13f, white, true))
        safe.addView(uiText("Backend address currently: $baseUrl\nThe Flask engine must be running on this phone for local requests to work.", 11f, muted))
        content.addView(safe)
    }

    private fun riskPage() {
        content.addView(uiText("RISK MANAGEMENT", 18f, white, true))
        val c = card()
        c.addView(uiText("EQUITY-BASED RISK", 14f, gold, true))
        c.addView(uiText("Risk sizing should adapt to the account equity you enter; no hardcoded $100 minimum. Broker minimum volume and contract specifications must be verified before calculating live lots.", 12f, muted))
        c.addView(uiText("• Risk per setup\n• Combined risk across batch orders\n• Maximum open setups\n• Daily loss limit\n• Stop loss / take profit\n• Emergency close-all requires separate confirmation", 12f, white))
        c.addView(uiText("These controls are design requirements and are not yet connected to live broker execution.", 11f, gold))
        content.addView(c)
        button(content, "Back to Settings", purple) { showPage("SETTINGS") }
    }

    private fun metricCard(title: String, value: String, color: Int): LinearLayout = card().apply {
        addView(uiText(title, 10f, muted, true)); addView(uiText(value, 21f, color, true))
    }

    private fun card(bg: Int = cardColor, border: Int = Color.rgb(91, 59, 156)): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(dp(14), dp(12), dp(14), dp(12))
        background = rounded(bg, border, 15)
        val lp = LinearLayout.LayoutParams(-1, -2); lp.topMargin = dp(10); lp.bottomMargin = dp(2)
        layoutParams = lp
    }

    private fun button(parent: LinearLayout, title: String, color: Int, action: () -> Unit) {
        val b = TextView(this).apply {
            text = title; gravity = Gravity.CENTER; textSize = 13f
            setTextColor(if (color == gold) Color.BLACK else white)
            setTypeface(null, android.graphics.Typeface.BOLD)
            background = rounded(color, color, 12)
            setPadding(dp(12), dp(13), dp(12), dp(13))
            setOnClickListener { action() }
        }
        parent.addView(b, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(8) })
    }

    private fun uiText(value: String, size: Float = 14f, color: Int = white, bold: Boolean = false): TextView = TextView(this).apply {
        text = value; textSize = size; setTextColor(color); setPadding(0, dp(5), 0, dp(5))
        if (bold) setTypeface(null, android.graphics.Typeface.BOLD)
    }

    private fun rounded(fill: Int, stroke: Int, radius: Int): GradientDrawable = GradientDrawable().apply {
        setColor(fill); setCornerRadius(dp(radius).toFloat()); setStroke(dp(1), stroke)
    }
    private fun dp(v: Number) = (v.toFloat() * resources.displayMetrics.density).toInt()

    private fun request(path: String, method: String = "GET", payload: JSONObject? = null): JSONObject {
        val connection = URL(baseUrl + path).openConnection() as HttpURLConnection
        try {
            connection.requestMethod = method; connection.connectTimeout = 15000; connection.readTimeout = 25000
            connection.setRequestProperty("Accept", "application/json")
            if (payload != null) {
                connection.doOutput = true; connection.setRequestProperty("Content-Type", "application/json")
                connection.outputStream.use { it.write(payload.toString().toByteArray(Charsets.UTF_8)) }
            }
            val code = connection.responseCode
            val stream = if (code in 200..299) connection.inputStream else connection.errorStream
            val body = stream?.bufferedReader()?.use { it.readText() } ?: "{}"
            val json = JSONObject(body)
            if (code !in 200..299) throw IOException(json.optString("reason", json.optString("message", "HTTP $code")))
            return json
        } finally { connection.disconnect() }
    }

    private fun perform(description: String, path: String, method: String = "GET", payload: JSONObject? = null, onSuccess: (JSONObject) -> Unit) {
        if (::messageView.isInitialized) messageView.text = description
        executor.execute {
            try { val result = request(path, method, payload); runOnUiThread { onSuccess(result) } }
            catch (e: Exception) { runOnUiThread {
                if (::decisionView.isInitialized) decisionView.text = "CONNECTION ERROR"
                if (::messageView.isInitialized) messageView.text = "${e.message}\n\nCheck Flask in Termux."
                if (::chartStatus.isInitialized && selectedPage == "CHART") chartStatus.text = "Feed unavailable: ${e.message}"
            } }
        }
    }

    private fun refreshStatus() {
        perform("Checking engine status…", "/status") { data ->
            if (::statusView.isInitialized) statusView.text = "SYSTEM: ${data.optString("status", "UNKNOWN")}"
        }
    }

    private fun saveSettings() {
        if (!::strategySpinner.isInitialized) return
        val payload = JSONObject().put("strategy", strategySpinner.selectedItem.toString()).put("execution", "MANUAL")
        perform("Saving settings…", "/settings", "POST", payload) { refreshStatus() }
    }

    private fun generateSignal() {
        if (!::equityInput.isInitialized || !::strategySpinner.isInitialized) return
        val equity = equityInput.text.toString().trim().toDoubleOrNull()
        if (equity == null || !equity.isFinite() || equity <= 0) {
            decisionView.text = "WAIT"; messageView.text = "Enter valid account equity first."; return
        }
        decisionView.text = "ANALYSING…"; detailsView.text = ""
        val payload = JSONObject().put("equity", equity).put("strategy", strategySpinner.selectedItem.toString())
        perform("Analyzing M5, M15, H1 and H4…", "/signal", "POST", payload) { data ->
            val d = data.optString("decision", "WAIT"); decisionView.text = d
            val lines = mutableListOf(data.optString("reason", "No confirmed setup."))
            listOf("entry" to "Entry", "stop_loss" to "Stop Loss", "take_profit_1" to "TP1", "take_profit_2" to "TP2", "take_profit_3" to "TP3").forEach { (key, label) -> if (data.has(key)) lines.add("$label: ${data.opt(key)}") }
            val risk = data.optJSONObject("risk"); if (risk != null) lines.add("Risk budget: ${risk.opt("risk_budget")} • ${risk.optString("risk_percent")}% • ${risk.optString("lot_size_status")}")
            lines.add("Broker execution: DISABLED")
            messageView.text = lines.joinToString("\n\n")
            val warnings = data.optJSONArray("warnings")
            detailsView.text = if (warnings == null || warnings.length() == 0) "" else (0 until warnings.length()).joinToString("\n") { "⚠ ${warnings.optString(it)}" }
        }
    }

    private fun startBot() { perform("Starting signal engine…", "/start", "POST", JSONObject()) { refreshStatus() } }
    private fun stopBot() { perform("Stopping new signal activity…", "/stop", "POST", JSONObject()) { if (::statusView.isInitialized) statusView.text = "SYSTEM: STOPPED" } }

    private fun loadCandles() {
        if (!::chartStatus.isInitialized || !::chartView.isInitialized) return
        val requestedTimeframe = selectedTimeframe
        chartStatus.text = "Loading XAUUSD ${requestedTimeframe} candles…"
        executor.execute {
            try {
                val result = request("/market-data?timeframe=$requestedTimeframe")
                val arr = result.optJSONArray("candles") ?: JSONArray()
                val candles = mutableListOf<Candle>()
                for (i in 0 until arr.length()) {
                    val o = arr.optJSONObject(i) ?: continue
                    candles.add(Candle(o.optDouble("open"), o.optDouble("high"), o.optDouble("low"), o.optDouble("close"), o.optString("openTime")))
                }
                val status = result.optString("status", "UNKNOWN")
                val count = result.optInt("candles_received", candles.size)
                runOnUiThread {
                    latestCandles = candles
                    chartView.setCandles(candles)
                    chartStatus.text = "${result.optString("symbol", "XAUUSD")} • $requestedTimeframe • $status • $count candles"
                    chartStatus.setTextColor(if (status == "LIVE_DATA_READY") teal else gold)
                }
            } catch (e: Exception) {
                runOnUiThread { chartStatus.text = "FEED UNAVAILABLE • ${e.message} • Showing last available candles"; chartStatus.setTextColor(Color.rgb(255, 112, 125)) }
            }
        }
    }

    override fun onResume() {
        super.onResume()
        if (selectedPage == "CHART") {
            chartRefreshHandler.removeCallbacks(chartRefreshTask)
            loadCandles()
            chartRefreshHandler.postDelayed(chartRefreshTask, chartRefreshIntervalMs)
        }
    }

    override fun onPause() {
        chartRefreshHandler.removeCallbacks(chartRefreshTask)
        super.onPause()
    }

    override fun onDestroy() {
        chartRefreshHandler.removeCallbacks(chartRefreshTask)
        executor.shutdown()
        super.onDestroy()
    }

    data class Candle(val open: Double, val high: Double, val low: Double, val close: Double, val time: String)

    inner class CandleChartView(context: android.content.Context) : View(context) {
        private var candles: List<Candle> = emptyList()
        private val grid = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.rgb(190, 145, 42); strokeWidth = dp(1).toFloat() }
        private val wick = Paint(Paint.ANTI_ALIAS_FLAG).apply { strokeWidth = dp(1.3f).toFloat() }
        private val body = Paint(Paint.ANTI_ALIAS_FLAG)
        private val label = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.rgb(83, 54, 7); textSize = dp(10).toFloat() }
        fun setCandles(value: List<Candle>) { candles = value; invalidate() }
        override fun onDraw(canvas: Canvas) {
            super.onDraw(canvas)
            canvas.drawColor(Color.rgb(255, 218, 112))
            val left = dp(8).toFloat(); val right = width - dp(48).toFloat(); val top = dp(12).toFloat(); val bottom = height - dp(24).toFloat()
            for (i in 0..5) {
                val y = top + (bottom - top) * i / 5f
                canvas.drawLine(left, y, right, y, grid)
                canvas.drawText("—", right + dp(5), y + dp(3), label)
            }
            if (candles.isEmpty()) {
                label.textSize = dp(13).toFloat(); canvas.drawText("Waiting for actual XAUUSD candles…", left + dp(8), height / 2f, label); label.textSize = dp(10).toFloat(); return
            }
            val visible = candles.takeLast(65)
            val minP = visible.minOf { it.low }; val maxP = visible.maxOf { it.high }; val range = (maxP - minP).coerceAtLeast(0.01)
            fun y(price: Double) = bottom - ((price - minP) / range * (bottom - top)).toFloat()
            val slot = (right - left) / visible.size
            visible.forEachIndexed { i, c ->
                val x = left + slot * (i + .5f)
                val up = c.close >= c.open
                val color = if (up) Color.rgb(104, 71, 8) else Color.rgb(177, 52, 27)
                wick.color = color; canvas.drawLine(x, y(c.high), x, y(c.low), wick)
                body.color = color
                val y1 = y(maxOf(c.open, c.close)); val y2 = y(minOf(c.open, c.close))
                canvas.drawRect(x - slot * .28f, y1, x + slot * .28f, maxOf(y1 + dp(2), y2), body)
            }
            val last = visible.last().close
            val line = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.rgb(113, 70, 0); strokeWidth = dp(1.5f).toFloat(); pathEffect = DashPathEffect(floatArrayOf(dp(5).toFloat(), dp(3).toFloat()), 0f) }
            canvas.drawLine(left, y(last), right, y(last), line)
            label.color = Color.rgb(74, 46, 0); label.typeface = Typeface.DEFAULT_BOLD
            canvas.drawText(String.format(Locale.US, "%.2f", last), right + dp(4), y(last) - dp(3), label)
        }
    }
}
