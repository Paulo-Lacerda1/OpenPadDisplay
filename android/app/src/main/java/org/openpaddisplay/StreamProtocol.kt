package org.openpaddisplay

import org.json.JSONObject
import java.io.DataInputStream

object StreamProtocol {
    const val MAX_FRAME = 8 * 1024 * 1024
    data class Header(val width: Int, val height: Int, val fps: Int, val source: String)
    data class Frame(val data: ByteArray, val ptsUs: Long)

    fun readHeader(input: DataInputStream): Header {
        val magic = ByteArray(8).also { input.readFully(it) }
        require(magic.contentEquals("OPAD0001".toByteArray(Charsets.US_ASCII))) { "Unsupported protocol" }
        val size = input.readInt()
        require(size in 1..4096) { "Invalid metadata size" }
        val json = JSONObject(ByteArray(size).also { input.readFully(it) }.toString(Charsets.UTF_8))
        require(json.getString("codec") == "h264") { "Unsupported codec" }
        return Header(json.getInt("width"), json.getInt("height"), json.getInt("fps"),
            json.optString("source", "test-pattern")).also {
            require(it.width in 2..4096 && it.height in 2..4096 && it.width % 2 == 0 && it.height % 2 == 0)
            require(it.fps in 1..144)
        }
    }

    fun readFrame(input: DataInputStream): Frame {
        val size = input.readInt()
        require(size in 1..MAX_FRAME) { "Invalid access unit size" }
        val pts = input.readLong()
        require(pts >= 0) { "Invalid presentation timestamp" }
        return Frame(ByteArray(size).also { input.readFully(it) }, pts)
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
