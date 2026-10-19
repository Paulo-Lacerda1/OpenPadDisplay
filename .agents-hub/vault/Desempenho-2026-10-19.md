# Desempenho — 2026-10-19

Relacionado: [[Projeto]] · [[Tarefas]] · [[Decisões]] · [[Contexto]]

## Pedido e coordenação

Melhorar a aplicação, desempenho primeiro; bónus isolados noutra branch, sem push.
Codex coordena host/integração, Copilot Android/tablet e revisão host, OpenCode foi
solicitado para revisão independente e teste comportamental. As reservas do Hub
protegem os ficheiros no checkout partilhado.

Branch de desempenho: `perf/pipeline-and-decoder-overhead`.

## Plano e achados

1. Medir pipeline completo sem confundir taxa pedida/painel/render callbacks com
   frames distintos apresentados. O tablet `4cbdde5d` foi detetado, NVENC disponível.
2. Descartar frames raw excedentes antes de `videoconvert`, mantendo a fila raw
   limitada e sem descartar unidades H.264 dependentes.
3. Substituir pad-probe Python por frame por amostragem dos contadores nativos de
   `identity.stats`; desativar sinais handoff sem consumidor.
4. Mover callbacks MediaCodec do main looper para HandlerThread por sessão,
   aguardando a limpeza mesmo em interrupção/erro de release.
5. Expor rate_dropped, ocupação raw_queue e máximo de tempo de write_frame por
   intervalo para separar descarte/captura/transporte em investigações futuras.

A cópia raw `pipewiresrc always-copy=true` é candidata relevante (~9,83 MB por
frame BGRA 1920×1280), mas permanece por validar lifetime/benchmark de captura.
Evitar chamar a isto causa demonstrada do limite desktop. A cópia de dados H.264
e alocações ByteArray Android são muito menores (~3 MB/s a 24 Mbit/s) e ficaram
para medição posterior.

## Evidência inicial

- 12 testes Linux passaram com `OPENPADDISPLAY_TEST_NVENC=1` e
  `OPENPADDISPLAY_TEST_VIRTUAL=1`: framing, SPS/PPS/IDR, timestamps, fallback,
  descodificação ffmpeg NVENC, criação/remoção virtual e negociação 144 Hz.
- Experimento 320×240, fonte144 limitada60: ordem antiga 144 buffers no converter
  e60 codificados; nova 60 no converter e60 codificados (58,3% menos invocações).
  Não corresponde a uma redução de CPU global; fonte sem formato explícito pode
  negociar passthrough. O teste de regressão deve forçar BGRA→I420 para conversão real.
- Experimento adicional BGRA→I420 1920×1280 com 288 buffers de origem: ambos
  codificam120; antigo converte172 (fila descarta restante), novo converte120.
  CPU de processo observado236,7% vs203,3%, porém com desktop/compilações ativos:
  números exploratórios, não comparação isolada nem promessa de ganho global.
- Benchmark host-only NVENC scroll144/24Mbit:143,99 FPS; CPU80,4% com sessão
  virtual e aplicações concorrentes. Confirma capacidade neste ensaio, sem ganho
  CPU demonstrado contra baseline isolada.
- Copilot: build/instalação Android e stream virtual verificados; `gfxinfo` é UI,
  não prova de cadência do vídeo. Ensaio alternativo USB inicialmente inconclusivo;
  Codex repete sob controlo e restaura mapping/sessão originais.

## Validação independente

Copilot reviu `video.py`: sem regressão funcional evidente; confirmou semântica
da ordem rate/convert e monotonicidade dos contadores no GStreamer1.24 local.
`identity.stats` requer GStreamer≥1.20. `send_max_ms` mede envio apenas, nunca
latência ponta a ponta. Alterações/documentação em `docs/performance.md`.

## Resultado validado

- 13/13 testes passaram, todos os opt-ins GPU/virtual ativos, sem skips.
- Teste novo `linux/tests/test_video.py` força BGRA→I420, protege fonte de perdas
  por scheduling, e verifica saídas60, conversões60, contadores nativos e PTS
  únicos/ordenados. Executado também com ordem antiga injetada: falha144≠60,
  como esperado; fonte60 continua correta.
- USB16s com scroll1920×1280/144FPS/24Mbit/s: host144,0FPS estáveis após startup;
  Android143,7–144,3FPS recebidos/callbacks; painel144Hz. CPU58,3–63,5% por
  intervalo, raw_queue0, rate_dropped0, send_max0,19–0,28ms. Sem comparação CPU
  antes/depois isolada, nem prova de scanouts distintos/latência ponta a ponta.
- Mapping `tcp:27183→tcp:27183`, app e sessão virtual originais restaurados.
- APK com HandlerThread novo instalado no tablet; build validado pelo Copilot.

## Entrega

- Desempenho: commit local `b777e68`, branch `perf/pipeline-and-decoder-overhead`.
- Bónus: commit local `a5f332d`, branch `feat/display-resolution-presets`, worktree
  `/home/paulo/Desktop/OpenPadDisplay-bonus`. Launcher oferece 960×640, 1440×960 e
  1920×1280 (default); mantém 60/120/144 Hz e bitrate existente.
- Copilot implementou o bónus; Codex reviu e executou smoke GTK/Xvfb independente
  com todas as 9 combinações, argumentos e bitrate exatos, seletores bloqueados
  durante sessão, repostos ao terminar e sensíveis após falha de arranque. Nenhum
  host ou monitor foi criado neste smoke.
- Menor resolução reduz carga de captura/conversão/codificação, mas bitrate fixo
  não garante menor consumo USB. O preset maior não é descrito como resolução
  nativa do painel.
- Sem push; worktree do bónus limpa; árvore principal apenas mantém o vault não
  versionado já existente. Sessão USB/desktop do utilizador preservada.

## Revisão independente posterior — OpenCode

OpenCode concluiu a revisão do host e comunicou que `test_video.py` e os testes
de protocolo/encoder passaram: 10 testes executados, 3 ignorados por configuração
do ambiente. Não encontrou regressões na ordem rate→videoconvert nem nos
contadores `identity.stats`. Esta execução é adicional aos 13 testes com todos
os opt-ins aprovados por Codex; não substitui nem amplia o seu alcance. Não
houve alterações de código nem push nesta revisão.
