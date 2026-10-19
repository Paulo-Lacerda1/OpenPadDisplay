package org.openpaddisplay

import org.json.JSONObject
import java.io.DataInputStream

object StreamProtocol {
    const val MAX_FRAME = 8 * 1024 * 1024
    const val MAX_METADATA = 4096
    data class Header(val width: Int, val height: Int, val fps: Int, val source: String, val encoder: String,
                      val version: Int = 1, val testId: String = "", val testDurationSeconds: Int = 0)
    data class Frame(val data: ByteArray, val ptsUs: Long)
    data class HostStats(val sequence: Long, val intervalSeconds: Double,
                         val captureFps: Double, val encodedFps: Double,
                         val rateDropped: Long, val rawQueue: Int, val sendMaxMs: Double,
                         val bitrateMbps: Double, val cpuPercent: Double)
    data class TestComplete(val testId: String, val durationSeconds: Int, val elapsedSeconds: Double)

    fun readHeader(input: DataInputStream): Header {
        val magic = ByteArray(8).also { input.readFully(it) }
        val version = when (magic.toString(Charsets.US_ASCII)) {
            "OPAD0001" -> 1
            "OPAD0002" -> 2
            else -> error("Unsupported protocol")
        }
        val size = input.readInt()
        require(size in 1..4096) { "Invalid metadata size" }
        val json = JSONObject(ByteArray(size).also { input.readFully(it) }.toString(Charsets.UTF_8))
        require(json.getString("codec") == "h264") { "Unsupported codec" }
        val hasTestId = json.has("test_id")
        require(hasTestId == json.has("test_duration_seconds")) { "Incomplete timed test header" }
        return Header(json.getInt("width"), json.getInt("height"), json.getInt("fps"),
            json.optString("source", "test-pattern"), json.optString("encoder", "unknown"), version,
            if (hasTestId) json.getString("test_id") else "",
            if (hasTestId) json.getInt("test_duration_seconds") else 0).also {
            require(it.width in 2..4096 && it.height in 2..4096 && it.width % 2 == 0 && it.height % 2 == 0)
            require(it.fps in 1..144)
            if (hasTestId) {
                require(it.version == 2 && it.source == "test-pattern") { "Timed tests require a v2 test pattern" }
                require(it.testId.isNotBlank() && it.testId.length <= 128) { "Invalid test identifier" }
                require(it.testDurationSeconds in 1..3600) { "Invalid test duration" }
            }
        }
    }

    fun readFrame(input: DataInputStream, version: Int = 1, onTestComplete: (TestComplete) -> Unit = {},
                  onHostStats: (HostStats) -> Unit = {}): Frame? {
        require(version in 1..2) { "Unsupported protocol" }
        // Bound consecutive metadata records so a broken peer cannot starve video.
        repeat(16) {
            val type = if (version == 2) input.readUnsignedByte() else 1
            val size = input.readInt()
            val maxSize = when (type) {
                1 -> MAX_FRAME
                2, 3 -> MAX_METADATA
                else -> 0
            }
            require(type in 1..3) { "Unsupported record type" }
            require(size in 1..maxSize) { "Invalid record size" }
            val pts = input.readLong()
            require(pts >= 0) { "Invalid presentation timestamp" }
            val payload = ByteArray(size).also { input.readFully(it) }
            when (type) {
                1 -> return Frame(payload, pts)
                2 -> onHostStats(readHostStats(payload))
                3 -> {
                    onTestComplete(readTestComplete(payload))
                    return null
                }
            }
        }
        error("Too many metadata records without video")
    }

    private fun readHostStats(payload: ByteArray): HostStats {
        val json = JSONObject(payload.toString(Charsets.UTF_8))
        fun number(key: String): Double = json.getDouble(key).also {
            require(it.isFinite() && it >= 0) { "Invalid host metric: $key" }
        }
        return HostStats(json.getLong("sequence"), number("interval_seconds"),
            number("capture_fps"), number("encoded_fps"), json.getLong("rate_dropped"),
            json.getInt("raw_queue"), number("send_max_ms"), number("bitrate_mbps"), number("cpu_percent")).also {
            require(it.sequence > 0 && it.intervalSeconds > 0 && it.rateDropped >= 0 && it.rawQueue in 0..2) {
                "Invalid host telemetry"
            }
        }
    }

    private fun readTestComplete(payload: ByteArray): TestComplete {
        val json = JSONObject(payload.toString(Charsets.UTF_8))
        require(json.getString("event") == "test_complete") { "Unexpected test record event" }
        val testId = json.getString("test_id")
        require(testId.isNotEmpty()) { "Test record missing test_id" }
        val durationSeconds = json.getInt("duration_seconds")
        require(durationSeconds in 1..3600) { "Invalid test duration" }
        val elapsedSeconds = json.getDouble("elapsed_seconds")
        require(elapsedSeconds.isFinite() && elapsedSeconds >= durationSeconds.toDouble()) {
            "Elapsed seconds must be >= duration_seconds"
        }
        return TestComplete(testId, durationSeconds, elapsedSeconds)
    }

    // Extract Annex-B SPS/PPS, accepting both three- and four-byte start codes.
    fun codecData(data: ByteArray): Pair<ByteArray, ByteArray> {
        val units = mutableListOf<Pair<Int, Int>>()
        var i = 0
        while (i + 3 <= data.size) {
            val prefix = when {
                i + 4 <= data.size && data[i] == 0.toByte() && data[i + 1] == 0.toByte() &&
                    data[i + 2] == 0.toByte() && data[i + 3] == 1.toByte() -> 4
                data[i] == 0.toByte() && data[i + 1] == 0.toByte() && data[i + 2] == 1.toByte() -> 3
                else -> 0
            }
            if (prefix > 0 && i + prefix < data.size) {
                units.add(i to prefix)
                i += prefix
            } else i++
        }
        fun find(type: Int): ByteArray {
            val index = units.indexOfFirst { (offset, prefix) -> (data[offset + prefix].toInt() and 31) == type }
            require(index >= 0) { "First frame must contain SPS and PPS" }
            val start = units[index].first
            val end = units.getOrNull(index + 1)?.first ?: data.size
            return data.copyOfRange(start, end)
        }
        return find(7) to find(8)
    }
}
