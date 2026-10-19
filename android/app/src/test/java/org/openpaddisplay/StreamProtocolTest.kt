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
            val frame = StreamProtocol.readFrame(input(version), version)!!
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
        val frame = StreamProtocol.readFrame(DataInputStream(ByteArrayInputStream(bytes)), 2, onHostStats = { host = it })!!
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

    private val testComplete = """{"event":"test_complete","test_id":"abc123","duration_seconds":10,"elapsed_seconds":10.5}"""

    private fun timedHeader(version: Int, fields: String, source: String = "test-pattern"): StreamProtocol.Header {
        val metadata = """{"codec":"h264","width":320,"height":240,"fps":60,"source":"$source",$fields}""".toByteArray()
        val bytes = ByteArrayOutputStream()
        DataOutputStream(bytes).use {
            it.write("OPAD000$version".toByteArray())
            it.writeInt(metadata.size)
            it.write(metadata)
        }
        return StreamProtocol.readHeader(DataInputStream(ByteArrayInputStream(bytes.toByteArray())))
    }

    @Test fun timedHeaderRequiresV2PatternAndPairedIdentifierDuration() {
        val fields = """"test_id":"abc123","test_duration_seconds":10"""
        val header = timedHeader(2, fields)
        assertEquals("abc123", header.testId)
        assertEquals(10, header.testDurationSeconds)
        for ((version, invalid, source) in listOf(
            Triple(1, fields, "test-pattern"), Triple(2, fields, "virtual"),
            Triple(2, """"test_id":"abc123"""", "test-pattern"),
            Triple(2, """"test_duration_seconds":10""", "test-pattern"),
            Triple(2, fields.replace("abc123", ""), "test-pattern"),
            Triple(2, fields.replace(":10", ":0"), "test-pattern"))) {
            assertThrows(IllegalArgumentException::class.java) { timedHeader(version, invalid, source) }
        }
    }

    @Test fun prematureCompletionCannotClaimFullDuration() {
        val payload = testComplete.replace("10.5", "9.9").toByteArray()
        assertThrows(IllegalArgumentException::class.java) {
            StreamProtocol.readFrame(input(2, type = 3, size = payload.size, payload = payload), 2)
        }
    }

    @Test fun testCompleteRecordIsTerminalAndNeverReturnedAsVideo() {
        var result: StreamProtocol.TestComplete? = null
        val bytes = input(2, type = 3, size = testComplete.toByteArray().size, payload = testComplete.toByteArray()).readBytes() +
            input(2).readBytes()
        val frame = StreamProtocol.readFrame(DataInputStream(ByteArrayInputStream(bytes)), 2,
            onTestComplete = { result = it })
        assertNull(frame)
        assertEquals("abc123", result!!.testId)
        assertEquals(10, result.durationSeconds)
        assertEquals(10.5, result.elapsedSeconds, 0.001)
    }

    @Test fun testCompleteRecordIsPassedToCallbackWithoutVideoAfter() {
        var result: StreamProtocol.TestComplete? = null
        val bytes = input(2, type = 3, size = testComplete.toByteArray().size, payload = testComplete.toByteArray()).readBytes()
        // Sem vídeo após o record3: readFrame processa o record3 e chama o callback.
        val frame = StreamProtocol.readFrame(DataInputStream(ByteArrayInputStream(bytes)), 2,
            onTestComplete = { result = it })
        assertNull(frame)
        assertEquals("abc123", result!!.testId)
        assertEquals(10, result.durationSeconds)
        assertEquals(10.5, result.elapsedSeconds, 0.001)
    }

    @Test fun testCompleteRecordWithInvalidEventIsRejected() {
        val bad = testComplete.replace("\"test_complete\"", "\"other_event\"")
        val stream = input(2, type = 3, size = bad.toByteArray().size, payload = bad.toByteArray())
        assertThrows(IllegalArgumentException::class.java) {
            StreamProtocol.readFrame(stream, 2, onTestComplete = { })
        }
    }

    @Test fun testCompleteRecordWithEmptyTestIdIsRejected() {
        val bad = testComplete.replace("\"abc123\"", "\"\"")
        val stream = input(2, type = 3, size = bad.toByteArray().size, payload = bad.toByteArray())
        assertThrows(IllegalArgumentException::class.java) {
            StreamProtocol.readFrame(stream, 2, onTestComplete = { })
        }
    }

    @Test fun testCompleteRecordWithInvalidDurationIsRejected() {
        val bad = testComplete.replace("\"duration_seconds\":10", "\"duration_seconds\":0")
        val stream = input(2, type = 3, size = bad.toByteArray().size, payload = bad.toByteArray())
        assertThrows(IllegalArgumentException::class.java) {
            StreamProtocol.readFrame(stream, 2, onTestComplete = { })
        }
    }

    @Test fun testCompleteRecordWithNaNElapsedIsRejected() {
        val bad = testComplete.replace("\"elapsed_seconds\":10.5", "\"elapsed_seconds\":NaN")
        val stream = input(2, type = 3, size = bad.toByteArray().size, payload = bad.toByteArray())
        assertThrows(IllegalArgumentException::class.java) {
            StreamProtocol.readFrame(stream, 2, onTestComplete = { })
        }
    }

    @Test fun recordType4IsRejected() {
        val baos = java.io.ByteArrayOutputStream()
        baos.write(4)
        baos.write(ByteArray(4) { 0 })
        baos.write(ByteArray(8) { 0.toByte() })
        baos.write(0)
        assertThrows(IllegalArgumentException::class.java) {
            StreamProtocol.readFrame(DataInputStream(java.io.ByteArrayInputStream(baos.toByteArray())), 2)
        }
    }

    @Test fun unboundedTelemetryCannotStarveVideo() {
        val one = input(2, type = 2, size = telemetry.toByteArray().size, payload = telemetry.toByteArray()).readBytes()
        val stream = DataInputStream(ByteArrayInputStream((1..16).fold(byteArrayOf()) { bytes, _ -> bytes + one }))
        assertThrows(IllegalStateException::class.java) { StreamProtocol.readFrame(stream, 2) }
    }
}
