# Diagnóstico acessível

Relacionado: [[Projeto]] · [[Tarefas]] · [[Decisões]] · [[Desempenho-2026-10-19]]

## Pedido e coordenação

O utilizador pediu implementar a ideia 6: painel opcional Android e teste guiado
para investigar captura, codificação, transmissão, descodificação e apresentação.
OpenCode já criou `bonus/diagnostico-painel-gargalo` a partir da main `a757c47`
(inclui a posição do monitor) e reservou os ficheiros Android/host do fluxo.
Codex aceitou rever e validar; não altera os ficheiros reservados por OpenCode.
O nome final previsto é `feat/diagnostics-panel`, seguindo a preferência por
nomes sem `bonus`. Sem push.

Codex prepara `docs/diagnostics.md` e validação no tablet. Antes de integrar,
confirmar o desenho de telemetria: o protocolo v1 atual só envia H.264 e metadata
inicial; não inserir novos tipos de registo sem versão/negociação explícita.
Cliente novo deve poder usar sessões antigas e mostrar dados indisponíveis.

## Critérios de revisão

- Painel opcional, ocultável, controlos acessíveis, conteúdo rolável.
- Contadores distintos de leitura de AU completa, submissão, saída do decoder e
  callbacks de apresentação. Atualizações UI por intervalo, não por frame.
- Reiniciar métricas e teste guiado por sessão; interromper teste ao desligar,
  reconectar ou sair para segundo plano.
- Diferenças de contadores incluem frames em trânsito e atraso de callbacks;
  não são uma medição de perdas TCP. Só rotular descartes quando medidos.
- Não concluir captura/codificação/transmissão apenas pelo FPS recebido no
  tablet. Hipóteses requerem fonte animada, métricas host e comparação de etapas.
- Cadência pedida, callbacks, frequência do painel e scanouts distintos são
  medidas diferentes. Desktop parado produz poucos frames intencionalmente.

## Referência consultada

[Android MediaCodec.OnFrameRenderedListener](https://developer.android.com/reference/android/media/MediaCodec.OnFrameRenderedListener)
documenta callbacks informativos que podem ser atrasados/agrupados; antes de
Android 14 alguns frames renderizados podem não gerar callback. O contador não
prova apresentação física distinta nem latência ponta a ponta.

## Estado

Documento de diagnóstico preparado; implementação OpenCode e desenho do fluxo
aguardam revisão. Não houve ainda validação do novo APK.

Codex implementou o motor puro Kotlin `GuidedDiagnosis.kt` e 13 testes JVM
(`GuidedDiagnosisTest.kt`), com `testImplementation` JUnit4.13.2. Todos os testes
passaram. API `evaluate(Observation(...), motionConfirmed).toDisplayText()`;
recebe médias por intervalo, métricas opcionais do host e contagem/duração da
recolha. Requer pelo menos 5 amostras/5 segundos; evita diagnóstico de desktop
parado, falsa atribuição de perdas, captura/encoder sem telemetria, inferências
de scanout e diagnóstico definitivo a partir de escrita máxima isolada.
OpenCode recebeu o contrato para integrar; os seus ficheiros mantêm-se reservados.

### Referência antes das alterações Android

Ensaio de 12 segundos com APK instalado v0.3.0/code3, fonte scroll1920×1280,
144 FPS pedidos, NVENC24Mbit/s e USB: após arranque, host144,0FPS,
CPU55,7–61,5%, Android143,5–144,5FPS recebidos/callbacks, painel144Hz. Sem
rate drops e fila raw0 nos relatórios; envio máximo0,14–0,25ms. Não mede
scanouts distintos nem latência ponta a ponta. Mapping original restaurado,
sem alterar definições dos monitores (fonte test-pattern).

## Entrega final

Codex continuou a implementação num worktree isolado após não receber plano nem
alterações dos ficheiros reservados por OpenCode. Os ficheiros deste agente no
checkout principal ficaram intactos. As cópias temporárias de guia/motor/testes
de Codex no checkout principal foram removidas após guardar o trabalho final.

- Branch **`feat/diagnostics-panel`**, commit **`9d654b6`**.
- Worktree final: **`/home/paulo/Desktop/OpenPadDisplay-diagnostics`**.
- Checkout principal continua em `bonus/diagnostico-painel-gargalo`, no commit
  base `a757c47`, sem alterações de código pendentes. Não trocar essa branch ou
  reaplicar a implementação inicial sem coordenar a entrega já existente.
- Sem push. Atalho do menu atualizado para o worktree final. Launcher antigo
  estava inativo e foi reaberto com o código novo; nenhuma sessão real ativa
  foi interrompida nessa reabertura.

### Comportamento entregue

- APK **0.4.0/code4** instalado no tablet; SHA-256 coincide com o build final.
- Botão **Diagnóstico** mostra/oculta painel rolável e guarda a visibilidade.
  O painel foi deixado oculto após os ensaios. O vídeo continua imersivo.
- Métricas locais: AUs completamente recebidas, submissões, saídas do decoder,
  callbacks de apresentação, frequência do painel, totais, espera de entrada,
  encoder e decoder efetivos. Contagem fora do main looper; UI por intervalo,
  sem atualizar texto do painel quando está oculto.
- Métricas host opcionais: captura, codificados/enviados, descartes raw por
  cadência, fila, envio máximo, bitrate e CPU. Dados stale após 5s ficam
  indisponíveis. **Perdas USB não são medidas**; diferenças de contadores não
  são apresentadas como perdas.
- Teste guiado de 15s: 3s de estabilização, recolha seguinte, médias ponderadas
  e hipóteses conservadoras. No desktop requer confirmação de movimento. Fica
  interrompido ao pausar/desligar/reconectar e não mistura sessões.
- Preferência de telemetria no launcher: **Enviar métricas ao tablet (APK 0.4+)**,
  desligada por defeito para preservar APKs antigos. CLI: `--diagnostics`.

### Protocolo e compatibilidade

Default v1 preservado. V2 explícito usa magic `OPAD0002` e registos tipados
`!BIQ`: tipo1 H.264, tipo2 JSON de telemetria (máx4096). Primeiro registo é
vídeo/SPS/PPS/IDR. Cliente novo aceita v1/v2; APK antigo rejeita v2 logo no magic.
Tipos/tamanhos/PTS/métricas finitas/seq crescente validados; dados de telemetria
nunca entram no decoder. Limite de metadados consecutivos evita starvation.
Teste guiado deduplica sequência host antes de somar descartes/ponderar médias.

Ver `/home/paulo/Desktop/OpenPadDisplay-diagnostics/protocol/README.md` e
`/home/paulo/Desktop/OpenPadDisplay-diagnostics/docs/diagnostics.md`.

### Validação final

- **36 testes Linux sem skips**, com GPU/NVENC, GTK/Xvfb e monitores GNOME reais:
  `PYTHONPATH=linux OPENPADDISPLAY_TEST_NVENC=1 OPENPADDISPLAY_TEST_VIRTUAL=1 OPENPADDISPLAY_TEST_DESKTOP=1 xvfb-run -a /usr/bin/python3 -m unittest discover -s linux/tests -v`.
- **21 testes JVM Android**: 13 casos de interpretação, 8 de framing/parser,
  versões, telemetria, tamanhos, truncamento, SPS/PPS e metadados excessivos.
- `assembleDebug`, `testDebugUnitTest` e `lintDebug` passaram. Lint sem erros;
  avisos não bloqueadores de texto/i18n, ícones e APIs desaconselhadas.
- Tablet real em USB, v2, padrão scroll1920×1280/144FPS/NVENC24Mbit/s: painel
  aberto manteve aproximadamente144FPS recebidos/saídas/callbacks e host144FPS.
  Não representa prova de scanouts físicos ou comparação causal de CPU.
- Teste guiado terminou com 12 amostras/12,01s após warmup; resultado
  «Sem limitação evidente nas métricas». Passar a segundo plano interrompeu o
  teste; reconexão reiniciou contadores (724 recebidos contra milhares antes).
- Servidor anterior v1 do checkout principal transmitiu para APK novo sem
  erros; painel indicou métricas host indisponíveis. A versão final reinstalada
  passou abrir/ocultar painel e mostrou dados atuais imediatamente.
- Screenshots/UIAutomator inspecionados, `git diff --check` limpo, worktree
  final limpo. Servidores de ensaio encerrados; mapping original
  `tcp:27183→tcp:27183` reposto. Não foi necessário mudar configuração guardada
  de ecrãs do GNOME nos ensaios de vídeo.


## Correção solicitada: controlo só no computador

Relacionado: [[Projeto]] · [[Decisões]] · [[Tarefas]].

- O utilizador não quer qualquer botão no tablet. Commit `b50774b` na mesma branch `feat/diagnostics-panel`, worktree `/home/paulo/Desktop/OpenPadDisplay-diagnostics`; sem push.
- APK **0.4.1/code5** remove todos os botões, checkbox e controlos de teste do tablet. Começa só com vídeo, ignorando a antiga preferência de visibilidade do APK0.4.0.
- Launcher: botão **Mostrar métricas no tablet / Ocultar métricas do tablet** altera a visibilidade imediatamente via broadcast ADB, sem reiniciar o socket/codec/vídeo. A resposta do APK confirma o estado; falhas USB/APKs antigos são mostrados no PC, não assumidos como sucesso. Receiver dinâmico limitado a emissores com `android.permission.DUMP` (ADB shell).
- Telemetria v2 passa a estar ativa nas sessões do launcher mesmo com sobreposição oculta; CLI mantém v1 por defeito e `--diagnostics` opt-in. Estado reaplicado após reconexão, limpo ao desligar; controlo de ocultação continua disponível durante interrupções do vídeo se o ADB responder.
- Teste guiado e confirmação de movimento foram transferidos para o PC; recolha Android continua 15s/warmup3s, resultados voltam ao PC e nunca ocupam o tablet. Cancelamento e sessões continuam separados.
- Validação: **40 testes Linux sem skips**, incluindo GTK/Xvfb, NVENC e monitores reais; **21 testes JVM**, assembleDebug e lintDebug aprovados. Teste GTK cobre mostrar/ocultar sem trocar o processo, resposta falhada e respostas antigas após interrupção. Testes ADB cobrem confirmação, versão antiga, timeout, resposta inválida e retorno do teste guiado.
- Ensaio real: launcher1920×1280/144Hz/esquerda, clique PC mostra métricas sem botões Android, clique oculta mantendo mesmo processo host. UIAutomator confirmou estado oculto com apenas layouts e SurfaceView, sem texto ou controlos; screenshots inspecionadas. Teste guiado15s com janela animada temporária no monitor virtual apresentou resultado no PC com tablet limpo. Animação removida no fim; não é prova de scanouts144FPS.
- APK instalado e hash SHA256 idêntico ao artefacto final: `2cebb4c4f8c91b5564d90205acd7be7b18f9c97fd978901aa03608ecd0dae793`. Launcher relançado com código final; ligação reposta e métricas desativadas.


## Teste automático RGB10s

O teste manual do launcher foi substituído conforme pedido: botão **Testar ligação (10 s)** transmite barras SMPTE a deslocarem-se lateralmente, recolhe diagnóstico automaticamente e repõe a sessão anterior. APK0.4.2/code6 instalado; commit `b6d77a8`, sem push. Equipa Codex/Copilot/OpenCode; resultados, limites e validação detalhados em [[Teste-RGB-10s]], relacionado com [[Projeto]] e [[Tarefas]].
