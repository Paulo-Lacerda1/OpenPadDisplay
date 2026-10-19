package org.openpaddisplay

import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.DataInputStream
import java.io.DataOutputStream
import org.junit.Assert.*
import org.junit.Test

class StreamProtocolTest {
    private fun input(version: Int, type: Int = 1, size: Int = 5, pts: Long = 1234,
                      payload: ByteArray = byteArrayOf(0, 0, 0, 1, 0x65)): DataInputStream {
        val bytes = ByteArrayOutputStream()
        DataOutputStream(bytes).use {
            if (version == 2) it.writeByte(type)
            it.writeInt(size)
            it.writeLong(pts)
            it.write(payload)
        }
        return DataInputStream(ByteArrayInputStream(bytes.toByteArray()))
    }

    @Test fun legacyAndV2VideoKeepAccessUnitAndTimestamp() {
        for (version in 1..2) {
            val frame = StreamProtocol.readFrame(input(version), version)
            assertEquals(1234L, frame.ptsUs)
            assertArrayEquals(byteArrayOf(0, 0, 0, 1, 0x65), frame.data)
        }
    }

    @Test fun invalidTypesAndSizesAreRejectedBeforeAllocation() {
        for ((version, stream) in listOf(2 to input(2, type = 9), 2 to input(2, size = Int.MAX_VALUE),
            2 to input(2, type = 2, size = 4097), 1 to input(1, size = -1),
            1 to input(1, size = 0), 1 to input(1, pts = -1))) {
            assertThrows(IllegalArgumentException::class.java) { StreamProtocol.readFrame(stream, version) }
        }
    }

    @Test fun truncatedAccessUnitEndsTheSession() {
        assertThrows(java.io.EOFException::class.java) { StreamProtocol.readFrame(input(1, size = 100)) }
    }

    @Test fun annexBConfigurationAcceptsThreeAndFourByteStartCodes() {
        val data = byteArrayOf(0, 0, 0, 1, 0x67, 42, 0, 0, 1, 0x68, 43, 0, 0, 0, 1, 0x65, 44)
        val (sps, pps) = StreamProtocol.codecData(data)
        assertArrayEquals(byteArrayOf(0, 0, 0, 1, 0x67, 42), sps)
        assertArrayEquals(byteArrayOf(0, 0, 1, 0x68, 43), pps)
    }

    private val telemetry = """{"sequence":1,"interval_seconds":2.0,"capture_fps":144.0,"encoded_fps":144.0,"rate_dropped":0,"raw_queue":0,"send_max_ms":0.25,"bitrate_mbps":24.0,"cpu_percent":60.0}"""

    @Test fun bothHeaderVersionsPreserveMetadataAndAnnounceTheirVersion() {
        val metadata = """{"codec":"h264","width":1920,"height":1280,"fps":144,"source":"test-pattern","encoder":"nvenc"}""".toByteArray()
        for (version in 1..2) {
            val bytes = ByteArrayOutputStream()
            DataOutputStream(bytes).use {
                it.write("OPAD000$version".toByteArray())
                it.writeInt(metadata.size)
                it.write(metadata)
            }
            val header = StreamProtocol.readHeader(DataInputStream(ByteArrayInputStream(bytes.toByteArray())))
            assertEquals(version, header.version)
            assertEquals(144, header.fps)
            assertEquals("nvenc", header.encoder)
        }
    }

    @Test fun telemetryIsParsedAndNeverReturnedAsVideo() {
        val bytes = input(2, type = 2, size = telemetry.toByteArray().size, payload = telemetry.toByteArray()).readBytes() +
            input(2).readBytes()
        var host: StreamProtocol.HostStats? = null
        val frame = StreamProtocol.readFrame(DataInputStream(ByteArrayInputStream(bytes)), 2) { host = it }
        assertArrayEquals(byteArrayOf(0, 0, 0, 1, 0x65), frame.data)
        assertEquals(144.0, host!!.captureFps, .01)
        assertEquals(1L, host!!.sequence)
    }

    @Test fun invalidHostMetricsAreRejected() {
        for (payload in listOf(telemetry.replace("144.0", "-1.0"),
            telemetry.replace("\"sequence\":1", "\"sequence\":0"),
            telemetry.replace("\"raw_queue\":0", "\"raw_queue\":3"))) {
            val stream = input(2, type = 2, size = payload.toByteArray().size, payload = payload.toByteArray())
            assertThrows(IllegalArgumentException::class.java) { StreamProtocol.readFrame(stream, 2) }
        }
    }

    @Test fun unboundedTelemetryCannotStarveVideo() {
        val one = input(2, type = 2, size = telemetry.toByteArray().size, payload = telemetry.toByteArray()).readBytes()
        val stream = DataInputStream(ByteArrayInputStream((1..16).fold(byteArrayOf()) { bytes, _ -> bytes + one }))
        assertThrows(IllegalStateException::class.java) { StreamProtocol.readFrame(stream, 2) }
    }
}
