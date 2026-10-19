# Decisões

Relacionado: [[Projeto]] · [[Contexto]]

Regista aqui cada decisão, a razão e os ficheiros afetados.

## 2026-10-19 — Callbacks Android fora do main looper

- **Decisão:** usar um `HandlerThread` dedicado por sessão para `MediaCodec.setOnFrameRenderedListener`.
- **Razão:** a versão anterior publicava um callback por frame no `main looper` (até 144 callbacks/s) apenas para incrementar um contador, competindo com a UI. O contador continua atómico e a thread é terminada com `quitSafely` após `codec.release`, aguardando o teardown.
- **Ficheiros:** `android/app/src/main/java/org/openpaddisplay/StreamClient.kt`.
- **Validação:** `./gradlew :app:assembleDebug`, instalação via ADB e stream real a 1920×1280/144 FPS no tablet; não interpretar `gfxinfo` da Activity como métrica direta do vídeo.

## 2026-10-19 — Reduzir processamento antes de otimizar transporte

- **Decisão:** `videorate` passa antes de `videoconvert`; contagem de captura usa `identity.stats` nativo e não pad-probe Python por frame. Fila raw mantém limite2; AUs H.264 dependentes não são descartadas.
- **Razão:** evitar conversão de frames que seriam descartados e callbacks Python na captura. Teste comportamental BGRA→I420 confirma60 conversões para60 saídas com fonte144, contra144 anteriormente.
- **Medição:** novos logs distinguem descartes por rate, fila raw e máximo de tempo de envio. `send_max_ms` não mede latência total.
- **Limite:** manter `always-copy=true` até medir captura real e lifetime; não inferir scanouts distintos de callbacks/painel.
- **Resultado:** commit `b777e68`; 13 testes GPU/virtual aprovados e ensaio USB144FPS. Ver [[Desempenho-2026-10-19]].

## 2026-10-19 — Isolamento dos bónus e reservas

- Melhorias de desempenho em `perf/pipeline-and-decoder-overhead`; seletor de resolução só em `feat/display-resolution-presets`, worktree `/home/paulo/Desktop/OpenPadDisplay-bonus`. Sem push.
- O Hub rejeita reservas com caminho absoluto fora do projeto e não existe painel na worktree. A equipa coordena as edições físicas apenas na worktree e reserva os caminhos relativos equivalentes no projeto principal (`desktop.py`/`README.md`), evitando alterações concorrentes desses caminhos em ambas as árvores.

## 2026-10-19 — Posição do monitor e preservação do ambiente de trabalho

- **Decisão:** seletor com esquerda/direita/acima/abaixo e esquema visual; preferência XDG guardada atomicamente e reaplicada por sessão. Branch `feat/monitor-position`, baseada na main que já integrou as melhorias anteriores; sem push.
- **Âmbito:** posição na extremidade do grupo de ecrãs, preservando o grupo; GNOME Wayland existente, sem alteração do APK. Trabalho realizado por Codex sem delegação, conforme pedido.
- **Descoberta:** a criação/remoção de monitores virtuais pode provocar reorganização automática GNOME. Capturar a disposição antes da criação, não apenas antes da chamada que aplica a posição.
- **Ciclo de vida:** método temporário 1 de `ApplyMonitorsConfig`; guardar modos/escala/rotação/primário e posições relativas; verificar se o utilizador alterou a disposição antes de parar PipeWire. Restaurar a disposição original após remoção quando ainda for aplicável, incluindo rejeição da colocação e falhas do consumidor.
- **Validação:** 31 testes sem skips e ensaio no tablet; coordenadas e limpeza/restauro verificados. Ver [[Posicao-do-monitor]].

## 2026-10-19 — Diagnóstico opcional com telemetria v2 explícita

- **Decisão:** APK0.4 aceita v1/v2; host mantém v1 por defeito e envia v2 apenas com `--diagnostics` ou a opção no launcher. Não inserir telemetria num fluxo H.264 v1.
- **Métricas:** separar receção, submissão, saídas do decoder e callbacks; mostrar descartes raw medidos e marcar perdas USB como não medidas. Não inferir scanouts distintos ou latência total destes contadores.
- **Teste:** 15s com warmup3s; exige movimento no desktop, cancela em pausa/reconexão, não mistura sessões, não atribui gargalo sem métricas suficientes. Host sequência deduplicada nas médias/descartes.
- **Entrega:** implementação Codex isolada para preservar reservas OpenCode, branch `feat/diagnostics-panel`, commit `9d654b6`; worktree `/home/paulo/Desktop/OpenPadDisplay-diagnostics`. Atalho e APK instalados. Sem push.
- **Validação:** 36 testes Linux e 21 JVM sem falhas, build/lint, painel e teste guiado reais em USB, compatibilidade com servidor v1 e aproximadamente144FPS com painel aberto. Ver [[Diagnostico-acessivel]].


## 2026-10-19 — Tablet limpo e diagnóstico controlado pelo computador

- Pedido explícito do utilizador substitui o desenho anterior: retirar o botão Diagnóstico e todos os controlos do tablet. Apenas métricas sobre o vídeo quando o botão do launcher está ativo; vídeo limpo quando está desligado.
- Usar a ligação ADB já autorizada para comandos de visibilidade e teste, com confirmação de estado; não reiniciar vídeo nem alterar o protocolo para controlar a UI. Receiver limitado à permissão DUMP do shell.
- O launcher envia v2 sempre para permitir ativação durante uma sessão; CLI v1 por defeito preservada. Teste guiado e resultado ficam no computador.
- Commit `b50774b`, APK0.4.1 instalado, sem push. 40 testes Linux, 21 JVM, build/lint e cliques reais PC/tablet aprovados. Ver [[Diagnostico-acessivel]] e [[Projeto]].


## 2026-10-19 — Teste automático RGB de10s e conclusão explícita

- Pedido do utilizador substitui o teste manual por padrão SMPTE em scroll10s iniciado no botão PC; trabalho distribuído pelos3 agentes selecionados. Fonte controlada não mede captura PipeWire.
- Header v2 identifica teste/duração; record terminal3 confirma conclusão antes do EOF. Android não trata interrupção como sucesso; resultado associa o mesmo test_id ao resumo host.
- Worker termina a fonte temporária antes do restauro, mas Popen do restauro ocorre na thread GTK após verificar fecho/desligar. Preservar modo/posição/métricas e bloquear controlos de modo enquanto ligado.
- Commit `b6d77a8`, APK0.4.2 instalado; sem push. Duas execuções10,007s, cancelamento real, monitores e tablet limpo verificados. 30 JVM e testes Linux/GTK/GPU, incluindo reexecução isolada de um timeout transitório GNOME. Ver [[Teste-RGB-10s]] e [[Projeto]].
