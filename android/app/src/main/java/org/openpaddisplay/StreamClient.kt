package org.openpaddisplay

import android.media.MediaCodec
import android.media.MediaCodecInfo
import android.media.MediaCodecList
import android.media.MediaFormat
import android.os.Handler
import android.os.Build
import android.os.Looper
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
    private val onStatus: (String) -> Unit
) {
    private val running = AtomicBoolean(false)
    @Volatile private var socket: Socket? = null
    private var worker: Thread? = null

    fun start() {
        if (!running.compareAndSet(false, true)) return
        worker = Thread({
            while (running.get()) {
                try {
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
                    if (running.get()) onStatus("${error.message ?: error.javaClass.simpleName}\nRetrying in 2 seconds…")
                } finally {
                    socket = null
                }
                if (running.get()) {
                    try { Thread.sleep(2000) } catch (_: InterruptedException) { break }
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
        val sourceName = when (header.source) {
            "virtual" -> "Extended desktop"
            "test-pattern" -> "Test pattern"
            else -> "Video"
        }
        onHeader(header)
        if (Build.VERSION.SDK_INT >= 31) {
            surface.setFrameRate(header.fps.toFloat(), Surface.FRAME_RATE_COMPATIBILITY_FIXED_SOURCE,
                Surface.CHANGE_FRAME_RATE_ALWAYS)
        } else {
            surface.setFrameRate(header.fps.toFloat(), Surface.FRAME_RATE_COMPATIBILITY_FIXED_SOURCE)
        }
        val first = StreamProtocol.readFrame(input)
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
        val rendered = AtomicLong(0)
        var drainThread: Thread? = null
        try {
            codec.configure(format, surface, null, 0)
            codec.setOnFrameRenderedListener({ _, _, _ -> rendered.incrementAndGet() }, Handler(Looper.getMainLooper()))
            codec.start()
            draining.set(true)
            drainThread = Thread({
                val bufferInfo = MediaCodec.BufferInfo()
                try {
                    while (draining.get() && running.get()) {
                        val index = codec.dequeueOutputBuffer(bufferInfo, 10_000)
                        if (index >= 0) codec.releaseOutputBuffer(index, bufferInfo.size > 0)
                    }
                } catch (error: Exception) {
                    drainError.set(error)
                    try { connection.close() } catch (_: Exception) { }
                }
            }, "OpenPadDisplay-decoder").also { it.start() }
            var frame = first
            var received = 0L
            var lastReceived = 0L
            var lastRendered = 0L
            var lastReport = System.nanoTime()
            while (running.get()) {
                var index = -1
                val deadline = System.nanoTime() + 3_000_000_000L
                while (running.get() && index < 0) {
                    drainError.get()?.let { throw it }
                    check(System.nanoTime() < deadline) { "Decoder input timed out" }
                    index = codec.dequeueInputBuffer(10_000)
                }
                if (!running.get()) break
                val buffer = checkNotNull(codec.getInputBuffer(index))
                buffer.clear()
                require(frame.data.size <= buffer.remaining()) { "Decoder buffer too small for access unit" }
                buffer.put(frame.data)
                codec.queueInputBuffer(index, 0, frame.data.size, frame.ptsUs, 0)
                received++
                val now = System.nanoTime()
                if (now - lastReport >= 1_000_000_000L) {
                    val seconds = (now - lastReport) / 1e9
                    val count = rendered.get()
                    onStatus("$sourceName · ${header.width}×${header.height} · requested ${header.fps} FPS\n" +
                        "Received %.1f · rendered callbacks %.1f FPS\n%s".format(
                            (received - lastReceived) / seconds, (count - lastRendered) / seconds,
                            "Host: ${header.encoder} · decoder: ${info.name}"))
                    lastReport = now
                    lastReceived = received
                    lastRendered = count
                }
                frame = StreamProtocol.readFrame(input)
            }
        } finally {
            draining.set(false)
            // Only the receiver thread releases the codec, after the drain thread exits.
            var interrupted = false
            while (drainThread?.isAlive == true) {
                try { drainThread.join() } catch (_: InterruptedException) { interrupted = true }
            }
            try { codec.stop() } catch (_: IllegalStateException) { }
            codec.release()
            if (interrupted) Thread.currentThread().interrupt()
        }
    }
}
