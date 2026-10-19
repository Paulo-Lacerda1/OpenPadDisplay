package org.openpaddisplay

import android.media.MediaCodec
import android.media.MediaCodecInfo
import android.media.MediaCodecList
import android.media.MediaFormat
import android.os.Build
import android.os.Handler
import android.os.HandlerThread
import android.view.Surface
import java.io.DataInputStream
import java.net.InetSocketAddress
import java.net.Socket
import java.nio.ByteBuffer
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicLong
import java.util.concurrent.atomic.AtomicReference

class StreamClient(
    private val surface: Surface,
    private val onHeader: (StreamProtocol.Header) -> Unit,
    private val onStatus: (String) -> Unit,
    private val onDiagnostics: (Sample?) -> Unit = {},
    private val onTestComplete: (StreamProtocol.TestComplete) -> Unit = {}
) {
    data class Sample(
        val header: StreamProtocol.Header,
        val decoder: String,
        val hardwareDecoder: Boolean,
        val receivedFps: Double,
        val queuedFps: Double,
        val decodedFps: Double,
        val renderedFps: Double,
        val receivedTotal: Long,
        val queuedTotal: Long,
        val decodedTotal: Long,
        val renderedTotal: Long,
        val inputWaitMs: Double,
        val intervalSeconds: Double,
        val sampledAtNs: Long,
        val host: StreamProtocol.HostStats?,
        val hostAgeMs: Long?
    )

    private val running = AtomicBoolean(false)
    @Volatile private var socket: Socket? = null
    @Volatile private var fastReconnectUntilNs = 0L
    private var worker: Thread? = null

    fun start() {
        if (!running.compareAndSet(false, true)) return
        worker = Thread({
            while (running.get()) {
                try {
                    onDiagnostics(null)
                    onStatus("Connecting over USB…")
                    val connection = Socket()
                    socket = connection
                    connection.use {
                        if (!running.get()) return@use
                        it.tcpNoDelay = true
                        it.soTimeout = 5000
                        it.connect(InetSocketAddress("127.0.0.1", 27183), 3000)
                        receive(it)
                    }
                } catch (error: Exception) {
                    if (running.get()) {
                        onDiagnostics(null)
                        onStatus("${error.message ?: error.javaClass.simpleName}\nRetrying in 2 seconds…")
                    }
                } finally {
                    socket = null
                }
                if (running.get()) {
                    val delay = if (System.nanoTime() < fastReconnectUntilNs) 100L else 2000L
                    try { Thread.sleep(delay) } catch (_: InterruptedException) { break }
                }
            }
        }, "OpenPadDisplay-receiver").also { it.start() }
    }

    fun stop() {
        running.set(false)
        try { socket?.close() } catch (_: Exception) { }
        worker?.interrupt()
    }

    private fun receive(connection: Socket) {
        val input = DataInputStream(connection.getInputStream().buffered(64 * 1024))
        val header = StreamProtocol.readHeader(input)
        if (header.testId.isEmpty()) fastReconnectUntilNs = 0L
        var testCompleteReceived = false
        val latestHost = AtomicReference<StreamProtocol.HostStats?>(null)
        val hostSeenNs = AtomicLong(0)
        val received = AtomicLong(0)
        val queued = AtomicLong(0)
        val decoded = AtomicLong(0)
        val rendered = AtomicLong(0)
        val inputWaitNs = AtomicLong(0)
        fun readFrame(): StreamProtocol.Frame? {
            val frame = StreamProtocol.readFrame(input, header.version,
                onTestComplete = {
                    require(header.testId.isNotEmpty()) { "Test record without test_id in header" }
                    require(it.testId == header.testId) { "Test record test_id does not match header" }
                    require(it.durationSeconds == header.testDurationSeconds) {
                        "Test record duration does not match header"
                    }
                    require(received.get() > 0) { "Test record received before any video frame" }
                    require(!testCompleteReceived) { "Duplicate test record" }
                    testCompleteReceived = true
                    // Reopen the restored monitor promptly after this deliberate source switch.
                    fastReconnectUntilNs = System.nanoTime() + 3_000_000_000L
                    onTestComplete(it)
                },
                onHostStats = {
                    val previous = latestHost.get()
                    require(previous == null || it.sequence > previous.sequence) { "Host telemetry sequence did not increase" }
                    latestHost.set(it)
                    hostSeenNs.set(System.nanoTime())
                }
            )
            if (frame != null) received.incrementAndGet()
            return frame
        }
        onHeader(header)
        if (Build.VERSION.SDK_INT >= 31) {
            surface.setFrameRate(header.fps.toFloat(), Surface.FRAME_RATE_COMPATIBILITY_FIXED_SOURCE,
                Surface.CHANGE_FRAME_RATE_ALWAYS)
        } else {
            surface.setFrameRate(header.fps.toFloat(), Surface.FRAME_RATE_COMPATIBILITY_FIXED_SOURCE)
        }
        val first = readFrame() ?: error("No video frame received")
        val (sps, pps) = StreamProtocol.codecData(first.data)
        val info = MediaCodecList(MediaCodecList.REGULAR_CODECS).codecInfos
            .filter { !it.isEncoder && it.supportedTypes.any { type -> type.equals("video/avc", true) } }
            .sortedByDescending { it.isHardwareAccelerated }
            .firstOrNull {
                it.getCapabilitiesForType("video/avc").videoCapabilities
                    ?.areSizeAndRateSupported(header.width, header.height, header.fps.toDouble()) == true
            } ?: error("No H.264 decoder advertises ${header.width}×${header.height} @ ${header.fps}; lower server resolution/FPS")
        val format = MediaFormat.createVideoFormat("video/avc", header.width, header.height).apply {
            setByteBuffer("csd-0", ByteBuffer.wrap(sps))
            setByteBuffer("csd-1", ByteBuffer.wrap(pps))
            setInteger(MediaFormat.KEY_MAX_INPUT_SIZE, StreamProtocol.MAX_FRAME)
            setInteger(MediaFormat.KEY_FRAME_RATE, header.fps)
            if (info.getCapabilitiesForType("video/avc")
                    .isFeatureSupported(MediaCodecInfo.CodecCapabilities.FEATURE_LowLatency)) {
                setInteger(MediaFormat.KEY_LOW_LATENCY, 1)
            }
        }
        val codec = MediaCodec.createByCodecName(info.name)
        val draining = AtomicBoolean(false)
        val drainError = AtomicReference<Exception?>(null)
        var drainThread: Thread? = null
        val renderThread = HandlerThread("OpenPadDisplay-render-callbacks").also { it.start() }
        val renderHandler = Handler(renderThread.looper)
        val reporter = object : Runnable {
            var lastAt = System.nanoTime()
            var lastReceived = 0L
            var lastQueued = 0L
            var lastDecoded = 0L
            var lastRendered = 0L
            override fun run() {
                if (!running.get() || !draining.get()) return
                val now = System.nanoTime()
                val seconds = (now - lastAt) / 1e9
                val r = received.get()
                val q = queued.get()
                val d = decoded.get()
                val p = rendered.get()
                val hostAt = hostSeenNs.get()
                val sample = Sample(header, info.name, info.isHardwareAccelerated,
                    (r - lastReceived) / seconds, (q - lastQueued) / seconds,
                    (d - lastDecoded) / seconds, (p - lastRendered) / seconds,
                    r, q, d, p, inputWaitNs.getAndSet(0) / 1e6, seconds, now,
                    latestHost.get(), if (hostAt == 0L) null else (now - hostAt) / 1_000_000)
                onDiagnostics(sample)
                val source = if (header.source == "virtual") "Extended desktop" else "Test pattern"
                onStatus("$source · ${header.width}×${header.height} · requested ${header.fps} FPS\n" +
                    "Received %.1f · decoded %.1f · rendered callbacks %.1f FPS\nHost: %s · decoder: %s".format(
                        sample.receivedFps, sample.decodedFps, sample.renderedFps, header.encoder, info.name))
                lastAt = now
                lastReceived = r
                lastQueued = q
                lastDecoded = d
                lastRendered = p
                renderHandler.postDelayed(this, 1000)
            }
        }
        try {
            codec.configure(format, surface, null, 0)
            codec.setOnFrameRenderedListener({ _, _, _ -> rendered.incrementAndGet() }, renderHandler)
            codec.start()
            draining.set(true)
            renderHandler.postDelayed(reporter, 1000)
            drainThread = Thread({
                val bufferInfo = MediaCodec.BufferInfo()
                try {
                    while (draining.get() && running.get()) {
                        val index = codec.dequeueOutputBuffer(bufferInfo, 10_000)
                        if (index >= 0) {
                            val hasFrame = bufferInfo.size > 0 &&
                                bufferInfo.flags and MediaCodec.BUFFER_FLAG_CODEC_CONFIG == 0
                            if (hasFrame) decoded.incrementAndGet()
                            codec.releaseOutputBuffer(index, hasFrame)
                        }
                    }
                } catch (error: Exception) {
                    drainError.set(error)
                    try { connection.close() } catch (_: Exception) { }
                }
            }, "OpenPadDisplay-decoder").also { it.start() }
            var frame = first
            while (running.get()) {
                var index = -1
                val deadline = System.nanoTime() + 3_000_000_000L
                val waitStarted = System.nanoTime()
                while (running.get() && index < 0) {
                    drainError.get()?.let { throw it }
                    check(System.nanoTime() < deadline) { "Decoder input timed out" }
                    index = codec.dequeueInputBuffer(10_000)
                }
                inputWaitNs.addAndGet(System.nanoTime() - waitStarted)
                if (!running.get()) break
                val buffer = checkNotNull(codec.getInputBuffer(index))
                buffer.clear()
                require(frame.data.size <= buffer.remaining()) { "Decoder buffer too small for access unit" }
                buffer.put(frame.data)
                codec.queueInputBuffer(index, 0, frame.data.size, frame.ptsUs, 0)
                queued.incrementAndGet()
                val next = readFrame()
                if (next != null) frame = next
            }
        } finally {
            draining.set(false)
            renderHandler.removeCallbacks(reporter)
            var interrupted = false
            while (drainThread?.isAlive == true) {
                try { drainThread.join() } catch (_: InterruptedException) { interrupted = true }
            }
            try { codec.stop() } catch (_: IllegalStateException) { }
            renderThread.quitSafely()
            try { codec.release() } finally {
                while (renderThread.isAlive) {
                    try { renderThread.join() } catch (_: InterruptedException) { interrupted = true }
                }
                if (interrupted) Thread.currentThread().interrupt()
            }
        }
    }
}
