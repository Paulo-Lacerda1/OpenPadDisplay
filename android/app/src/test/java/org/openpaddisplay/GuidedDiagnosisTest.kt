package org.openpaddisplay

import org.junit.Assert.*
import org.junit.Test

class GuidedDiagnosisTest {
    private fun healthy() = GuidedDiagnosis.Observation(
        requestedFps = 144, source = "test-pattern", receivedFps = 144.0,
        decodedFps = 144.0, renderedCallbackFps = 144.0, panelHz = 144.0,
        captureFps = 144.0, encodedFps = 144.0, sampleCount = 10, durationSeconds = 10.0
    )

    @Test fun healthyStreamDoesNotClaimDistinctPhysicalFramesOrZeroLoss() {
        val result = GuidedDiagnosis.evaluate(healthy(), false)
        assertEquals("Sem limitação evidente nas métricas", result.headline)
        assertTrue(result.limitations.any { it.contains("não provam") })
        assertTrue(result.limitations.any { it.contains("não são medidas") })
    }

    @Test fun idleDesktopDoesNotGetDiagnosedAsCaptureFailure() {
        val result = GuidedDiagnosis.evaluate(healthy().copy(source = "virtual", receivedFps = 1.0,
            captureFps = 1.0, encodedFps = 1.0), false)
        assertEquals("Confirma movimento contínuo", result.headline)
        assertTrue(result.findings.isEmpty())
    }

    @Test fun absentHostTelemetryDoesNotIdentifyCaptureOrEncoderAsCause() {
        val result = GuidedDiagnosis.evaluate(healthy().copy(receivedFps = 60.0,
            captureFps = null, encodedFps = null), true)
        assertTrue(result.findings.any { it.contains("ainda não está identificada") })
        assertTrue(result.limitations.any { it.contains("não é possível separá-las") })
        assertFalse(result.findings.any { it.contains("limite na origem/captura") })
    }

    @Test fun shortOrInterruptedCollectionDoesNotProduceBottleneck() {
        val result = GuidedDiagnosis.evaluate(healthy().copy(sampleCount = 2, durationSeconds = 2.0), true)
        assertEquals("Recolha ainda incompleta", result.headline)
        assertTrue(result.findings.isEmpty())
    }

    @Test fun partialTelemetryStillReportsLowThroughputWithoutAssigningCause() {
        val result = GuidedDiagnosis.evaluate(healthy().copy(receivedFps = 60.0,
            decodedFps = 60.0, renderedCallbackFps = 60.0, captureFps = null, encodedFps = 60.0), true)
        assertEquals("Há sinais para investigar", result.headline)
        assertTrue(result.findings.any { it.contains("ainda não está identificada") })
    }

    @Test fun captureCandidateRequiresContinuousMotionAndEncoderTrackingIt() {
        val result = GuidedDiagnosis.evaluate(healthy().copy(source = "virtual", receivedFps = 60.0,
            decodedFps = 60.0, renderedCallbackFps = 60.0, captureFps = 60.0, encodedFps = 60.0), true)
        assertTrue(result.findings.any { it.contains("Possível limite na origem/captura") })
    }

    @Test fun slowHostOutputDoesNotPrematurelyBlameEncoder() {
        val result = GuidedDiagnosis.evaluate(healthy().copy(encodedFps = 60.0, sendMaxMs = 100.0), true)
        assertTrue(result.findings.any { it.contains("codificação ou contrapressão") })
    }

    @Test fun lowReceiverRateAllowsTransportAndDecoderBackpressure() {
        val result = GuidedDiagnosis.evaluate(healthy().copy(receivedFps = 60.0), true)
        assertTrue(result.findings.any { it.contains("transporte e entrada do decoder") })
        assertFalse(result.findings.any { it.contains("perda de pacotes") })
    }

    @Test fun delayedCallbacksDoNotCountAsLostFrames() {
        val result = GuidedDiagnosis.evaluate(healthy().copy(renderedCallbackFps = 70.0), true)
        assertTrue(result.findings.any { it.contains("notificações de apresentação") })
        assertTrue(result.nextSteps.any { it.contains("atrasados/agrupados") })
    }

    @Test fun decoderOutputAndPanelLimitAreIndependentSignals() {
        val result = GuidedDiagnosis.evaluate(healthy().copy(decodedFps = 60.0,
            renderedCallbackFps = 60.0, panelHz = 60.0), true)
        assertTrue(result.findings.any { it.contains("saída do decoder") })
        assertTrue(result.findings.any { it.contains("modo atual do painel") })
    }

    @Test fun rawCadenceDropsAreNotTransportFailures() {
        val result = GuidedDiagnosis.evaluate(healthy().copy(rawRateDropped = 42), true)
        assertEquals("Sem limitação evidente nas métricas", result.headline)
        assertTrue(result.findings.any { it.contains("não representa perdas USB") })
    }

    @Test fun unavailablePanelRateDoesNotMeanZeroHzPanel() {
        val result = GuidedDiagnosis.evaluate(healthy().copy(panelHz = 0.0), true)
        assertFalse(result.findings.any { it.contains("modo atual do painel") })
        assertTrue(result.limitations.any { it.contains("painel indisponível") })
    }

    @Test fun invalidMeasurementsAreRejected() {
        for (observation in listOf(healthy().copy(receivedFps = Double.NaN),
            healthy().copy(captureFps = -1.0), healthy().copy(requestedFps = 0))) {
            assertEquals("Métricas inválidas", GuidedDiagnosis.evaluate(observation, true).headline)
        }
    }
}
