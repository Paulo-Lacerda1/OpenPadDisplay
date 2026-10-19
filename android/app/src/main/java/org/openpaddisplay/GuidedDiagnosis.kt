package org.openpaddisplay

/** Conservative interpretation of interval averages, independent of Android UI. */
object GuidedDiagnosis {
    data class Observation(
        val requestedFps: Int,
        val source: String,
        val receivedFps: Double,
        val decodedFps: Double? = null,
        val renderedCallbackFps: Double? = null,
        val panelHz: Double? = null,
        val captureFps: Double? = null,
        val encodedFps: Double? = null,
        val rawRateDropped: Long? = null,
        val sendMaxMs: Double? = null,
        val sampleCount: Int = 0,
        val durationSeconds: Double = 0.0
    )

    data class Result(
        val headline: String,
        val findings: List<String>,
        val nextSteps: List<String>,
        val limitations: List<String>
    ) {
        fun toDisplayText(): String = listOf(
            headline,
            findings.joinToString("\n"),
            nextSteps.joinToString("\n"),
            limitations.joinToString("\n")
        ).filter { it.isNotBlank() }.joinToString("\n\n")
    }

    fun evaluate(observation: Observation, motionConfirmed: Boolean): Result {
        val limitations = mutableListOf(
            "Resultados indicativos: callbacks e Hz do painel não provam imagens físicas distintas.",
            "Diferenças entre contadores podem incluir frames pendentes; perdas TCP e latência total não são medidas."
        )
        val values = listOfNotNull(
            observation.receivedFps, observation.decodedFps, observation.renderedCallbackFps,
            observation.panelHz, observation.captureFps, observation.encodedFps, observation.sendMaxMs
        )
        if (observation.requestedFps !in 1..144 || values.any { !it.isFinite() || it < 0 } ||
            !observation.durationSeconds.isFinite() || observation.rawRateDropped?.let { it < 0 } == true) {
            return Result("Métricas inválidas", emptyList(), listOf("Repete a recolha numa nova sessão."), limitations)
        }
        if (observation.sampleCount < 5 || observation.durationSeconds < 5) {
            return Result("Recolha ainda incompleta", emptyList(),
                listOf("Mantém a ligação e recolhe pelo menos 5 segundos após o arranque."), limitations)
        }
        if (observation.source != "test-pattern" && !motionConfirmed) {
            return Result("Confirma movimento contínuo", emptyList(),
                listOf("Move uma janela durante o teste ou usa o padrão scroll no computador.",
                    "Um desktop parado envia poucos frames intencionalmente."), limitations)
        }

        val findings = mutableListOf<String>()
        val steps = mutableListOf<String>()
        var signals = 0
        val target = observation.requestedFps.toDouble()
        val capture = observation.captureFps
        val encoded = observation.encodedFps
        val decoded = observation.decodedFps
        val callbacks = observation.renderedCallbackFps
        val received = observation.receivedFps

        if (capture == null || encoded == null) {
            limitations += "Captura e codificação do host não estão ambas disponíveis; não é possível separá-las no tablet."
            steps += "Compara os contadores de captura/envio nos detalhes da ligação do computador."
        } else if (capture < target * .85 && kotlin.math.abs(encoded - capture) < target * .15) {
            signals++
            findings += "Possível limite na origem/captura: o encoder acompanha uma fonte abaixo do pedido."
            steps += "Compara o desktop animado com o padrão scroll e repete com menor resolução."
        } else if (capture >= target * .9 && encoded < capture * .85) {
            signals++
            findings += "A saída do host não acompanha a captura; codificação ou contrapressão precisam de investigação."
            steps += "Compara NVENC/x264, CPU e tempo de envio antes de atribuir o limite ao encoder."
        }

        if (encoded != null && encoded >= target * .9 && received < encoded * .85) {
            signals++
            findings += "O cliente não acompanha o envio do host; transporte e entrada do decoder são candidatos."
            steps += "Baixa o bitrate e observa a espera pelo decoder; um socket bloqueado também pode refletir contrapressão."
        } else if (received < target * .85 && signals == 0) {
            signals++
            findings += "A receção está abaixo do pedido; a origem dessa diferença ainda não está identificada."
        }

        if (decoded != null && received > 0 && decoded < received * .85) {
            signals++
            findings += "A saída do decoder ficou abaixo da receção durante a recolha."
            steps += "Repete com menor resolução/frequência e verifica o decoder selecionado."
        }
        if (callbacks != null && decoded != null && decoded > 0 && callbacks < decoded * .85) {
            signals++
            findings += "As notificações de apresentação ficaram abaixo das saídas do decoder."
            steps += "Observa mais intervalos: callbacks podem chegar atrasados/agrupados; verifica a composição e o modo do painel."
        }
        if (observation.panelHz?.let { it > 0 && it + 1 < target } == true) {
            signals++
            findings += "O modo atual do painel está abaixo da frequência pedida."
            steps += "Verifica a frequência selecionada e as opções de poupança de bateria do tablet."
        }
        observation.rawRateDropped?.takeIf { it > 0 }?.let {
            findings += "O host descartou $it frames raw por cadência; isto não representa perdas USB."
        }
        if (observation.sendMaxMs?.let { it > 2000 / target } == true) {
            findings += "Houve uma escrita demorada no host; um máximo isolado não identifica o gargalo."
        }
        if (decoded == null) limitations += "Saídas do decoder indisponíveis; não é possível isolar descodificação/apresentação."
        if (observation.panelHz == null || observation.panelHz == 0.0) limitations += "Frequência efetiva do painel indisponível."
        if (signals == 0) {
            findings.add(0, "Não há limitação evidente nas etapas medidas durante esta recolha.")
            steps += "Se notas falhas visuais, repete com animação contínua e compara vários intervalos."
        }
        return Result(if (signals == 0) "Sem limitação evidente nas métricas" else "Há sinais para investigar",
            findings, steps.distinct(), limitations)
    }
}
