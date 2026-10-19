# Tarefas

Relacionado: [[Projeto]] · [[Decisões]]

## A fazer

- [ ] Descrever o objetivo do projeto

## Em curso


- [ ] Próxima investigação: lifetime/cópia BGRA PipeWire e frames distintos/latência ponta a ponta; não há prova de desktop real144FPS sustentados.

## Concluído

- [x] Teste automático RGB de televisão em movimento durante10s
  - Equipa Codex/Copilot/OpenCode, commit `b6d77a8` em `feat/diagnostics-panel`; sem push. APK0.4.2 instalado e launcher atualizado.
  - Resultado no PC, cancelamento/restauro e tablet limpo validados no dispositivo;30 JVM,46 Linux exercitados (1 timeout GNOME revalidado isoladamente). Ver [[Teste-RGB-10s]].

- [x] Diagnóstico acessível com controlo no computador e tablet limpo
  - `feat/diagnostics-panel`, commit `9d654b6`, worktree `/home/paulo/Desktop/OpenPadDisplay-diagnostics`; sem push.
  - Correção `b50774b`: APK0.4.1 instalado, botão mostrar/ocultar e teste guiado no PC; tablet só mostra métricas quando pedido. 40 testes Linux, 21 JVM, build/lint e ensaio real aprovados. Ver [[Diagnostico-acessivel]].

- [x] Escolher e guardar posição do tablet no launcher
  - Branch local `feat/monitor-position`: esquerda/direita/acima/abaixo, esquema visual, preferência persistente e restauro da disposição anterior. Sem push.
  - 31 testes sem skips, monitores reais, GTK/Xvfb e ensaio USB aprovados. Sem delegação. Ver [[Posicao-do-monitor]].

- [x] Reduzir overhead de callbacks de renderização Android
  - Build, instalação e stream H.264 validados no tablet ligado; painel reportou 144 Hz e logs mantiveram receção/renderização.
- [x] Otimizar ordem de processamento raw e contagem de captura
  - Commit local `b777e68` em `perf/pipeline-and-decoder-overhead`; 13/13 testes incluindo GPU/virtual, novo teste rejeita ordem antiga. USB com padrão scroll144FPS validado, sem prometer cadência igual no desktop real.
  - Diagnóstico, plano e medições: [[Desempenho-2026-10-19]].
- [x] Bónus: selecionar resolução no launcher (960×640/1440×960/1920×1280)
  - Isolado em `feat/display-resolution-presets`, worktree `/home/paulo/Desktop/OpenPadDisplay-bonus`; sem push.
  - Copilot implementou, Codex reviu e validou9 combinações, argumentos/bitrate, bloqueio/restauro dos controlos e falha de arranque num smoke GTK/Xvfb sem lançar host.
