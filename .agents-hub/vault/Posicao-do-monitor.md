# Posição do monitor

Relacionado: [[Projeto]] · [[Tarefas]] · [[Decisões]] · [[Desempenho-2026-10-19]]

## Pedido e entrega

O utilizador escolheu a ideia 2: configurar a posição do tablet no launcher,
com esquema visual e preferência guardada. Implementação por Codex, sem delegar
nem enviar tarefas aos outros agentes, respeitando a instrução anterior.

Branch local: `feat/monitor-position`, baseada na `main` em `dedec97`, que já
inclui as melhorias de desempenho e os presets de resolução. Sem push.
Implementação principal no commit `45e5a84`.

## Comportamento

- Quatro opções: à esquerda, à direita, acima ou abaixo; esquema visual com
  computador/tablet. A seleção fica bloqueada durante a ligação.
- Preferência escrita atomicamente em `~/.config/openpaddisplay/settings.json`,
  respeitando `XDG_CONFIG_HOME`; default à direita e recuperação segura se o
  ficheiro estiver ausente ou inválido.
- Com vários monitores, o tablet fica na extremidade escolhida do grupo e
  partilha uma margem utilizável com um ecrã existente. As posições relativas,
  modos, escala, rotação e ecrã principal do grupo são preservados.
- CLI: `./scripts/extend-usb.sh --position left`, também `right/above/below`.
  O argumento só é válido com `--source virtual`; sem argumento mantém a
  colocação automática GNOME.
- Não é necessária atualização do APK. Reabrir o launcher no computador para
  carregar a nova interface; a sessão anterior ficou reposta e ativa.

## Decisões técnicas e descoberta importante

Mutter só expõe o novo monitor após negociação PipeWire. A posição é aplicada
após o primeiro frame codificado e antes do cabeçalho da sessão. O novo conector
virtual é identificado comparando os monitores antes/depois, sem assumir que
será sempre `Meta-0`; identificação ambígua aborta a colocação.

O GNOME pode reorganizar ecrãs existentes ao criar/remover um monitor virtual.
Foi observado nos testes com o portátil, HDMI e a sessão de tablet preexistente.
A implementação captura a disposição **antes** de criar a sessão e usa-a ao
aplicar a posição. Antes de parar PipeWire, verifica se o utilizador alterou a
disposição durante a sessão. Se não alterou, restaura a disposição original
depois de o monitor virtual desaparecer; caso tenha alterado ou a topologia
mude, evita reaplicar uma configuração desatualizada. Também prepara o restauro
se o compositor rejeitar a colocação, após a sua reorganização automática.

Usa `ApplyMonitorsConfig` temporário, método 1; não grava a configuração de
monitores do GNOME. Retenta serial desatualizado e respeita coordenadas
lógicas/físicas, escala e rotação. API privada GNOME Wayland; outros compositores
continuam fora do âmbito do backend existente.

## Validação

- 31 testes aprovados sem skips, incluindo GPU/NVENC, launcher GTK/Xvfb e
  monitores GNOME reais, com:
  `PYTHONPATH=linux OPENPADDISPLAY_TEST_NVENC=1 OPENPADDISPLAY_TEST_VIRTUAL=1 OPENPADDISPLAY_TEST_DESKTOP=1 xvfb-run -a /usr/bin/python3 -m unittest discover -s linux/tests -v`
- Cobertura: quatro posições, vários ecrãs, escala/rotação, preservação de modos
  e primário, identificação ambígua, serial desatualizado, preferência persistida
  e escrita atómica falhada, bloqueio de controlos, rejeição de configuração,
  limpeza normal e após falha do consumidor. Os testes reais verificam o
  restauro da disposição anterior e continuidade da captura após mover o ecrã.
- Ensaio USB no tablet `4cbdde5d`: monitor 960×640 a 60 Hz pedidos colocado
  **acima**, NVENC e decoder `c2.qti.avc.decoder`; imagem recebida e coordenadas
  reais verificadas. Tráfego de desktop praticamente parado não é benchmark FPS.
- Após ensaio, mapping `tcp:27183→tcp:27183`, app e posições originais de todos
  os monitores restaurados. Os testes finais também preservaram a disposição.
- Esquema/legendas/interface renderizados e inspecionados em GTK/Xvfb;
  `git diff --check` limpo. Aviso de depreciação `set_wmclass` já existia.

Ficheiros principais: `desktop.py`, `layout.py`, `preferences.py`, `virtual.py`,
`video.py`, `__main__.py`, testes e `README.md`.

A pré-visualização GTK exige `python3-gi-cairo` (inclui a dependência Pycairo).
O instalador passa a incluir o pacote, `doctor.py` verifica o binding e o launcher
declara explicitamente `gi.require_foreign("cairo")`. No computador atual os
bindings já estavam instalados. Ajuste final validado pelo smoke GTK e dry-run
do instalador; nenhuma instalação de pacotes foi necessária.
