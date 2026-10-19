# Teste RGB automático de 10 segundos

Relacionado: [[Projeto]] · [[Diagnostico-acessivel]] · [[Tarefas]] · [[Decisões]].

## Pedido e divisão de trabalho

- O utilizador quer o padrão de televisão com barras RGB a deslocarem-se lateralmente ao clicar Testar ligação, durante10s; pediu explicitamente trabalho pelos3 agentes.
- Codex: suporte host --duration, marcador explícito de conclusão, protocolo/docs, integração e validação USB final.
- Copilot: fluxo GTK parar→padrão scroll10s→restaurar, resultado no PC, cancelamento e gestão de processos, testes.
- OpenCode: recolha automática Android, validação do marcador/identidade, diagnóstico no PC e revisão independente do host.
- Branch `feat/diagnostics-panel`, worktree `/home/paulo/Desktop/OpenPadDisplay-diagnostics`, baseada em b50774b; sem push. Reservas lógicas no projeto principal, edições só na worktree.

## Decisões

- `videotestsrc pattern=smpte horizontal-speed=4` reproduz o padrão já mostrado. Teste de pixels na linha superior confirma movimento real das barras e canais RGB, sem confundir a zona de ruído com deslocamento.
- --duration10 é uma sessão única: até15s à espera do cliente, duração desde o primeiro frame enviado, saída após cleanup. Sem benchmark/fontevirtual nesse modo.
- Header v2 contém test_id e test_duration_seconds; record3 JSON test_complete confirma conclusão antes do EOF, evitando corrida entre o timer Android e o fecho do socket. Android cancela se não houver marcador válido.
- O teste padrão não mede captura PipeWire do desktop; mede a cadeia com fonte animada controlada. Não prova scanouts distintos, perdas USB zero ou latência ponta a ponta.
- Preservar modo, posição e opção de métricas da sessão anterior; manter tablet sem controlos. Falhas/cancelamento devem limpar temporário antes de restaurar; fechar/desligar não deve ressuscitar sessão.

## Resultado e entrega

- Commit local **b6d77a8**, branch `feat/diagnostics-panel`, worktree `/home/paulo/Desktop/OpenPadDisplay-diagnostics`; sem push. APK **0.4.2/code6** instalado; launcher atualizado e em execução a partir da worktree.
- Codex integrou/harmonizou as três frentes, completou a revisão dos casos de erro e fez a validação real. Copilot forneceu o fluxo GTK inicial e gestão de processos; OpenCode forneceu parsing/callbacks e recolha Android automática. Sem alterações ao checkout principal.
- Botão **Testar ligação (10 s)**: encerra fonte virtual, envia `test-pattern/scroll` no mesmo modo e configuração de encoder/bitrate, recebe resumo host e diagnóstico Android da mesma identidade e repõe a sessão original. Sem confirmação ou movimento manual. Resultado só no PC, tablet sempre sem botões.
- Restauro criado no callback GTK, após verificar stop/close; evita recriar monitor se o utilizador já o desligou/fechou. Temporário sempre terminado com espera e escalada SIGINT→SIGTERM→SIGKILL antes de reutilizar a porta. Leitura limitada a35s, arranque do teste espera cliente até15s.
- Snapshot do comando e visibilidade preservados; callbacks antigos identificam o processo e não mudam o estado da nova sessão. Cancelamento não mostra diagnóstico de sucesso. Falha ao restaurar liberta controlos e deixa botão Ligar tablet utilizável.
- Android recolhe automaticamente após header de teste, warmup2s, finaliza no marcador terminal3. Header inválido/incompleto, ID/duração divergentes, marcador prematuro e ausência de vídeo são rejeitados. EOF/pausa sem marcador cancela. Estado de conclusão separado por sessão; reconexão breve após conclusão acelera regresso ao monitor.

## Validação

- **30 testes JVM** aprovados; assembleDebug e lintDebug aprovados. Testes cobrem versões antigas, separação de metadados/vídeo, conclusão terminal antes do EOF, campos emparelhados de teste e rejeição de conclusão com elapsed menor que duração.
- **46 testes Linux executados**, incluindo NVENC, GTK/Xvfb e monitores reais. Na execução completa,45 passaram e1 ensaio de posição (below) falhou por timeout transitório do GNOME/remoção tardia. Reexecução isolada do teste com as quatro posições passou em4,65s. Inspeção confirmou apenas monitores físicos após limpeza; ensaio real verificou disposição idêntica antes/depois. Não houve alteração em virtual.py/layout.py nesta tarefa.
- GTK usa uma única aplicação de teste (sem GLib critical) e verifica10 cenários: sucesso, host falhado, ausência de resultado, JSON inválido, ID Android diferente, cancelar, desligar, fechar, restauro falhado e stop tardio antes do callback de restauro. Confirma processos terminados antes de restaurar, controlos/labels corretos e configuração capturada.
- Ensaio USB real pelo botão PC em1920×1280/144Hz/esquerda: **duas execuções completas**, durações host10,007017s e10,007034s, cerca143,999FPS e1442 frames. Android devolveu diagnóstico Sem limitação evidente nas métricas. Isto refere-se ao padrão, não a captura de desktop nem scanouts físicos.
- Screenshots reais mostram SMPTE/barras RGB com ruído de TV;3126/3200 posições da linha superior mudaram entre capturas (fora da zona de ruído), confirmando movimento lateral visível.
- Segunda execução automatizada confirmou IDs correspondentes, marcador completo, processo virtual novo, modo144Hz e disposição dos monitores reposta. Preparação/reconexão acrescentam tempo à operação (ciclo completo observado17,45s), mas transmissão do padrão é10s.
- Cancelamento real de terceira execução com métricas ativas: marcador não emitido, Android cancelled, nenhum diálogo de conclusão, sessão original reposta e opção de métricas preservada. No fim, métricas ocultadas e UIAutomator mostrou só layouts/SurfaceView, sem texto/controlos.
- SHA256 do APK instalado confere com o artefacto final: `cf876fe94195f16400c23e3e80e09dcbc6c397e4cf4c483924448822da04f763`.



Comandos de validação (a partir da worktree):

```bash
cd android && ./gradlew :app:assembleDebug :app:testDebugUnitTest :app:lintDebug --offline
PYTHONPATH=linux OPENPADDISPLAY_TEST_NVENC=1 OPENPADDISPLAY_TEST_VIRTUAL=1 OPENPADDISPLAY_TEST_DESKTOP=1 xvfb-run -a /usr/bin/python3 -m unittest discover -s linux/tests -v
PYTHONPATH=linux:linux/tests OPENPADDISPLAY_TEST_VIRTUAL=1 /usr/bin/python3 -m unittest test_virtual.VirtualDisplayTests.test_virtual_output_positions_and_cleanup -v
```

Executar os comandos Linux a partir da raiz (não dentro de android); os testes de monitores exigem sessão GNOME e ausência de stream ativo. O ensaio USB usou o launcher real via AT-SPI e confirmação via ADB, com capturas de ecrã e comparação da disposição dos monitores antes/depois.
