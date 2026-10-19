package org.openpaddisplay

import android.app.Activity
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
import android.widget.Button
import android.widget.CheckBox
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
    private lateinit var diagnosticsButton: Button
    private lateinit var metricsText: TextView
    private lateinit var stateText: TextView
    private lateinit var guidedButton: Button
    private lateinit var motionCheck: CheckBox
    private lateinit var resultText: TextView
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
            guidedButton.text = "Cancelar teste (${(15 - elapsed).toInt() + 1} s)"
            resultText.text = if (elapsed < 3) "A estabilizar a ligação…" else
                "A recolher métricas. Mantém o movimento contínuo."
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
        label("Diagnóstico da ligação", 21f)
        stateText = label("A ligar por USB…")
        metricsText = label("À espera de vídeo…").apply { setTextIsSelectable(true) }
        label("Teste guiado · 15 segundos", 18f)
        label("Usa uma imagem em movimento. Um desktop parado envia poucos frames por desenho.")
        motionCheck = CheckBox(this).apply {
            text = "Vou manter movimento contínuo durante o teste"
            setTextColor(Color.WHITE)
            content.addView(this)
        }
        guidedButton = Button(this).apply {
            text = "Testar ligação (15 s)"
            contentDescription = "Iniciar ou cancelar teste guiado da ligação"
            isEnabled = false
            setOnClickListener { if (testStartedNs == null) startTest() else cancelTest("Teste cancelado.") }
            content.addView(this)
        }
        resultText = label("As conclusões são hipóteses. Não medem latência total nem perdas USB.")
            .apply { setTextIsSelectable(true) }
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
            topMargin = dp(64); rightMargin = dp(12); leftMargin = dp(12); bottomMargin = dp(12)
        })
        diagnosticsButton = Button(this).apply {
            text = "Diagnóstico"
            contentDescription = "Mostrar ou ocultar diagnóstico da ligação"
            setOnClickListener { showDiagnostics(diagnostics.visibility != View.VISIBLE) }
        }
        canvas.addView(diagnosticsButton, FrameLayout.LayoutParams(-2, -2, Gravity.TOP or Gravity.END).apply {
            topMargin = dp(10); rightMargin = dp(12)
        })
        showDiagnostics(getPreferences(MODE_PRIVATE).getBoolean("diagnostics_visible", false), false)
    }

    private fun showDiagnostics(show: Boolean, remember: Boolean = true) {
        diagnostics.visibility = if (show) View.VISIBLE else View.GONE
        diagnosticsButton.text = if (show) "Ocultar diagnóstico" else "Diagnóstico"
        if (show) updatePanel()
        if (remember) getPreferences(MODE_PRIVATE).edit().putBoolean("diagnostics_visible", show).apply()
    }

    private fun fitDiagnostics() {
        if (!::diagnostics.isInitialized || canvas.width == 0 || canvas.height == 0) return
        val width = (canvas.width - canvas.paddingLeft - canvas.paddingRight - dp(24)).coerceAtLeast(1)
        val height = (canvas.height - canvas.paddingTop - canvas.paddingBottom - dp(88)).coerceAtLeast(1)
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
        guidedButton.isEnabled = sample != null
        if (sample == null) {
            stateText.text = "A aguardar ligação USB"
            metricsText.text = connectionMessage
            return
        }
        val header = sample.header
        stateText.text = "Ligado · ${header.width}×${header.height} · pedidos ${header.fps} FPS"
        val host = sample.host?.takeIf { (sample.hostAgeMs ?: Long.MAX_VALUE) <= 5000 }
        val hostText = if (host == null) {
            if (header.version == 1) "Métricas do computador indisponíveis nesta sessão.\nAtiva «Enviar métricas ao tablet» no launcher e volta a ligar."
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

    private fun startTest() {
        val sample = latest ?: return
        if (System.nanoTime() - sample.sampledAtNs > 3_000_000_000L) {
            resultText.text = "Amostras antigas. Aguarda a recuperação da ligação e repete."
            return
        }
        if (sample.header.source != "test-pattern" && !motionCheck.isChecked) {
            resultText.text = "Confirma movimento contínuo antes de iniciar: move uma janela ou usa o padrão scroll."
            return
        }
        readings.clear()
        testMotionConfirmed = motionCheck.isChecked
        testStartedNs = System.nanoTime()
        motionCheck.isEnabled = false
        handler.post(testTicker)
    }

    private fun cancelTest(message: String) {
        if (testStartedNs == null) return
        handler.removeCallbacks(testTicker)
        testStartedNs = null
        readings.clear()
        guidedButton.text = "Testar ligação (15 s)"
        motionCheck.isEnabled = true
        resultText.text = message
    }

    private fun finishTest() {
        val samples = readings.toList()
        testStartedNs = null
        guidedButton.text = "Testar ligação (15 s)"
        motionCheck.isEnabled = true
        val last = samples.lastOrNull()?.sample ?: latest
        if (last == null || samples.isEmpty()) {
            resultText.text = "Recolha insuficiente. Repete com a ligação ativa."
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
        resultText.text = result.toDisplayText()
        Log.i("OpenPadDisplay", "Guided diagnosis: ${result.headline}; samples=${samples.size}; seconds=$seconds")
        readings.clear()
    }

    private fun disconnect() {
        cancelTest("Teste interrompido: aplicação em segundo plano ou superfície removida.")
        generation++
        client?.stop(); client = null; latest = null
        if (::guidedButton.isInitialized) updatePanel()
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

    override fun onResume() { super.onResume(); active = true; connect() }
    override fun onPause() { active = false; disconnect(); super.onPause() }
    override fun surfaceCreated(holder: SurfaceHolder) { connect() }
    override fun surfaceChanged(holder: SurfaceHolder, format: Int, width: Int, height: Int) { }
    override fun surfaceDestroyed(holder: SurfaceHolder) { disconnect() }
}
