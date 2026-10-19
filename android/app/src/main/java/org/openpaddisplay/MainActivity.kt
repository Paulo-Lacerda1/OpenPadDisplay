package org.openpaddisplay

import android.app.Activity
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.Build
import android.util.Base64
import org.json.JSONObject
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.Gravity
import android.view.SurfaceHolder
import android.view.SurfaceView
import android.view.View
import android.view.WindowInsets
import android.view.WindowInsetsController
import android.view.WindowManager
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import kotlin.math.abs
import kotlin.math.min

class MainActivity : Activity(), SurfaceHolder.Callback {
    private lateinit var canvas: FrameLayout
    private lateinit var video: SurfaceView
    private lateinit var diagnostics: ScrollView
    private lateinit var metricsText: TextView
    private lateinit var stateText: TextView
    private var client: StreamClient? = null
    private var active = false
    private var generation = 0
    private var streamWidth = 1920
    private var streamHeight = 1280
    private var latest: StreamClient.Sample? = null
    private var connectionMessage = "A ligar por USB…"
    private val handler = Handler(Looper.getMainLooper())
    private var testStartedNs: Long? = null
    private var testMotionConfirmed = false
    private var testId = ""
    private var testState = "idle"
    private var testResult = ""
    private val controlReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            when (intent.getStringExtra("command")) {
                "metrics" -> showDiagnostics(intent.getBooleanExtra("visible", false))
                "start_test" -> {
                    if (testStartedNs != null) cancelTest("Teste substituído por uma nova recolha.")
                    testId = intent.getStringExtra("test_id") ?: ""
                    startTest(intent.getBooleanExtra("motion", false))
                }
                "cancel_test" -> if (intent.getStringExtra("test_id") == testId) cancelTest("Teste cancelado.")
            }
            val response = JSONObject().put("visible", diagnostics.visibility == View.VISIBLE)
                .put("test_id", testId).put("test_state", testState).put("test_result", testResult)
            resultCode = RESULT_OK
            resultData = "OPAD:" + Base64.encodeToString(response.toString().toByteArray(Charsets.UTF_8), Base64.NO_WRAP)
        }
    }
    private data class Reading(val sample: StreamClient.Sample, val panelHz: Double?)
    private val readings = mutableListOf<Reading>()
    private val testTicker = object : Runnable {
        override fun run() {
            val started = testStartedNs ?: return
            val elapsed = (System.nanoTime() - started) / 1e9
            if (elapsed >= 15) {
                finishTest()
                return
            }
            handler.postDelayed(this, 1000)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.setDecorFitsSystemWindows(false)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        canvas = FrameLayout(this).apply { setBackgroundColor(Color.BLACK) }
        canvas.setOnApplyWindowInsetsListener { view, insets ->
            val bars = insets.getInsets(WindowInsets.Type.systemBars() or WindowInsets.Type.displayCutout())
            view.setPadding(bars.left, bars.top, bars.right, bars.bottom)
            fitVideo()
            fitDiagnostics()
            insets
        }
        video = SurfaceView(this).also { it.holder.addCallback(this) }
        canvas.addView(video, FrameLayout.LayoutParams(-1, -1, Gravity.CENTER))
        createDiagnostics()
        canvas.addOnLayoutChangeListener { _, _, _, _, _, _, _, _, _ -> fitVideo(); fitDiagnostics() }
        setContentView(canvas)
        val filter = IntentFilter("org.openpaddisplay.CONTROL_DIAGNOSTICS")
        // ADB shell controls the overlay. The receiver exists only while this Activity exists.
        if (Build.VERSION.SDK_INT >= 33) registerReceiver(controlReceiver, filter, "android.permission.DUMP", null, Context.RECEIVER_EXPORTED)
        else @Suppress("UnspecifiedRegisterReceiverFlag") registerReceiver(controlReceiver, filter, "android.permission.DUMP", null)
    }

    private fun dp(value: Int) = (value * resources.displayMetrics.density).toInt()

    private fun createDiagnostics() {
        val content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(18), dp(14), dp(18), dp(18))
        }
        fun label(text: String, size: Float = 14f): TextView = TextView(this).apply {
            this.text = text
            textSize = size
            setTextColor(Color.WHITE)
            setPadding(0, dp(6), 0, dp(6))
            content.addView(this)
        }
        stateText = label("A ligar por USB…")
        metricsText = label("À espera de vídeo…")
        diagnostics = ScrollView(this).apply {
            isFillViewport = false
            addView(content)
            background = GradientDrawable().apply {
                setColor(Color.argb(240, 17, 23, 32))
                cornerRadius = dp(14).toFloat()
            }
            visibility = View.GONE
        }
        canvas.addView(diagnostics, FrameLayout.LayoutParams(dp(510), dp(620), Gravity.TOP or Gravity.END).apply {
            topMargin = dp(12); rightMargin = dp(12); leftMargin = dp(12); bottomMargin = dp(12)
        })
    }

    private fun showDiagnostics(show: Boolean) {
        diagnostics.visibility = if (show) View.VISIBLE else View.GONE
        if (show) updatePanel()
    }

    private fun fitDiagnostics() {
        if (!::diagnostics.isInitialized || canvas.width == 0 || canvas.height == 0) return
        val width = (canvas.width - canvas.paddingLeft - canvas.paddingRight - dp(24)).coerceAtLeast(1)
        val height = (canvas.height - canvas.paddingTop - canvas.paddingBottom - dp(24)).coerceAtLeast(1)
        val params = diagnostics.layoutParams as FrameLayout.LayoutParams
        val desiredWidth = min(dp(510), width)
        val desiredHeight = min(dp(620), height)
        if (params.width != desiredWidth || params.height != desiredHeight) {
            params.width = desiredWidth; params.height = desiredHeight
            diagnostics.layoutParams = params
        }
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) window.insetsController?.apply {
            systemBarsBehavior = WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            hide(WindowInsets.Type.systemBars())
        }
    }

    private fun fitVideo() {
        if (canvas.width == 0 || canvas.height == 0) return
        val availableWidth = canvas.width - canvas.paddingLeft - canvas.paddingRight
        val availableHeight = canvas.height - canvas.paddingTop - canvas.paddingBottom
        val scale = min(availableWidth.toFloat() / streamWidth, availableHeight.toFloat() / streamHeight)
        val width = (streamWidth * scale).toInt().coerceAtLeast(1)
        val height = (streamHeight * scale).toInt().coerceAtLeast(1)
        if (video.layoutParams.width != width || video.layoutParams.height != height) {
            video.layoutParams = FrameLayout.LayoutParams(width, height, Gravity.CENTER)
        }
    }

    private fun connect() {
        if (!active || !video.holder.surface.isValid || client != null) return
        val id = ++generation
        client = StreamClient(video.holder.surface, { header ->
            runOnUiThread {
                if (id == generation) {
                    cancelTest("Teste interrompido: começou uma nova sessão.")
                    latest = null
                    streamWidth = header.width; streamHeight = header.height
                    fitVideo(); requestDisplayMode(header.fps)
                    stateText.text = "Ligado · a aguardar métricas"
                }
            }
        }, { message ->
            runOnUiThread {
                if (id == generation) {
                    connectionMessage = message
                    Log.i("OpenPadDisplay", (message + " Panel: ${video.display?.refreshRate ?: 0f} Hz").replace('\n', ' '))
                    if (latest == null) updatePanel()
                }
            }
        }, { sample ->
            runOnUiThread {
                if (id == generation) {
                    latest = sample
                    if (sample == null) cancelTest("Teste interrompido: a ligação foi reiniciada.")
                    val started = testStartedNs
                    if (sample != null && started != null && (sample.sampledAtNs - started) / 1e9 >= 3) {
                        readings.add(Reading(sample, video.display?.refreshRate?.toDouble()))
                    }
                    updatePanel()
                }
            }
        }).also { it.start() }
    }

    private fun updatePanel() {
        if (diagnostics.visibility != View.VISIBLE) return
        val sample = latest
        if (sample == null) {
            stateText.text = "A aguardar ligação USB"
            metricsText.text = connectionMessage
            return
        }
        val header = sample.header
        stateText.text = "Ligado · ${header.width}×${header.height} · pedidos ${header.fps} FPS"
        val host = sample.host?.takeIf { (sample.hostAgeMs ?: Long.MAX_VALUE) <= 5000 }
        val hostText = if (host == null) {
            if (header.version == 1) "Métricas do computador indisponíveis nesta sessão.\nVolta a ligar pelo launcher atualizado no computador."
            else "Métricas do computador a aguardar ou desatualizadas."
        } else {
            "Computador · intervalo de %.1f s\nCaptura: %.1f · codificados/enviados: %.1f FPS\nDescartes raw por cadência: %d · fila raw: %d\nEnvio máximo: %.2f ms · %.2f Mbit/s · CPU: %.1f%%".format(
                host.intervalSeconds, host.captureFps, host.encodedFps, host.rateDropped,
                host.rawQueue, host.sendMaxMs, host.bitrateMbps, host.cpuPercent)
        }
        metricsText.text = (
            "Recebidos: %.1f FPS\nSubmetidos ao decoder: %.1f FPS\nSaídas do decoder: %.1f FPS\nApresentação (callbacks): %.1f FPS\nPainel: %.1f Hz\n" +
            "Total recebidos/saídas/callbacks: %d / %d / %d\nEspera por entrada do decoder: %.1f ms no intervalo\n" +
            "Encoder: %s\nDecoder: %s (%s)\nPerdas USB: não medidas\n\n%s\n\n" +
            "Callbacks podem chegar atrasados; não provam imagens físicas distintas."
        ).format(sample.receivedFps, sample.queuedFps, sample.decodedFps, sample.renderedFps,
            video.display?.refreshRate ?: 0f, sample.receivedTotal, sample.decodedTotal, sample.renderedTotal,
            sample.inputWaitMs, header.encoder, sample.decoder,
            if (sample.hardwareDecoder) "hardware" else "software", hostText)
    }

    private fun startTest(motionConfirmed: Boolean) {
        val sample = latest
        if (sample == null || System.nanoTime() - sample.sampledAtNs > 3_000_000_000L) {
            testState = "error"
            testResult = "Sem amostras recentes. Aguarda a recuperação da ligação e repete."
            return
        }
        if (sample.header.source != "test-pattern" && !motionConfirmed) {
            testState = "error"
            testResult = "Confirma movimento contínuo no computador antes de iniciar."
            return
        }
        readings.clear()
        testMotionConfirmed = motionConfirmed
        testState = "running"
        testResult = ""
        testStartedNs = System.nanoTime()
        handler.post(testTicker)
    }

    private fun cancelTest(message: String) {
        if (testStartedNs == null) return
        handler.removeCallbacks(testTicker)
        testStartedNs = null
        readings.clear()
        testState = "cancelled"
        testResult = message
    }

    private fun finishTest() {
        val samples = readings.toList()
        testStartedNs = null
        val last = samples.lastOrNull()?.sample ?: latest
        if (last == null || samples.isEmpty()) {
            testState = "error"
            testResult = "Recolha insuficiente. Repete com a ligação ativa."
            return
        }
        val seconds = samples.sumOf { it.sample.intervalSeconds }
        fun average(value: (StreamClient.Sample) -> Double) =
            samples.sumOf { value(it.sample) * it.sample.intervalSeconds } / seconds
        val hosts = samples.mapNotNull { reading ->
            reading.sample.host?.takeIf { (reading.sample.hostAgeMs ?: Long.MAX_VALUE) <= 5000 }
        }.distinctBy { it.sequence }
        val hostSeconds = hosts.sumOf { it.intervalSeconds }
        fun hostAverage(value: (StreamProtocol.HostStats) -> Double): Double? =
            if (hosts.isEmpty()) null else hosts.sumOf { value(it) * it.intervalSeconds } / hostSeconds
        val observation = GuidedDiagnosis.Observation(last.header.fps, last.header.source,
            average { it.receivedFps }, average { it.decodedFps }, average { it.renderedFps },
            samples.lastOrNull()?.panelHz, hostAverage { it.captureFps }, hostAverage { it.encodedFps },
            if (hosts.isEmpty()) null else hosts.sumOf { it.rateDropped }, hosts.maxOfOrNull { it.sendMaxMs },
            samples.size, seconds)
        val result = GuidedDiagnosis.evaluate(observation, testMotionConfirmed)
        testState = "completed"
        testResult = result.toDisplayText()
        Log.i("OpenPadDisplay", "Guided diagnosis: ${result.headline}; samples=${samples.size}; seconds=$seconds")
        readings.clear()
    }

    private fun disconnect() {
        cancelTest("Teste interrompido: aplicação em segundo plano ou superfície removida.")
        generation++
        client?.stop(); client = null; latest = null
        if (::diagnostics.isInitialized) updatePanel()
    }

    private fun requestDisplayMode(fps: Int) {
        val display = video.display ?: return
        val current = display.mode
        val mode = display.supportedModes.firstOrNull {
            it.physicalWidth == current.physicalWidth && it.physicalHeight == current.physicalHeight &&
                abs(it.refreshRate - fps) < 0.5f
        }
        window.attributes = window.attributes.apply { preferredDisplayModeId = mode?.modeId ?: 0 }
    }

    override fun onDestroy() {
        unregisterReceiver(controlReceiver)
        handler.removeCallbacks(testTicker)
        super.onDestroy()
    }

    override fun onResume() { super.onResume(); active = true; connect() }
    override fun onPause() { active = false; disconnect(); super.onPause() }
    override fun surfaceCreated(holder: SurfaceHolder) { connect() }
    override fun surfaceChanged(holder: SurfaceHolder, format: Int, width: Int, height: Int) { }
    override fun surfaceDestroyed(holder: SurfaceHolder) { disconnect() }
}
