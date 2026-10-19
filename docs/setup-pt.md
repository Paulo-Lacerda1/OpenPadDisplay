# Primeiro teste no Ubuntu e no tablet

O projeto permite testar um padrão de vídeo ou criar um segundo monitor real
no GNOME Wayland. Começa pelo padrão para confirmar USB e descodificação; depois
ativa o ambiente de trabalho estendido, como explicado na secção 4.

## 1. Dependências no Ubuntu

Na raiz do repositório:

```bash
sudo apt update
sudo apt install adb usbutils python3-gi gir1.2-gstreamer-1.0 \
  gir1.2-gst-plugins-base-1.0 gstreamer1.0-tools \
  gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-ugly
./scripts/doctor.sh
```

O diagnóstico lê a sessão gráfica, as ferramentas, os elementos GStreamer,
os dispositivos ADB e a árvore USB. Não altera o GNOME nem cria monitores.
`nvh264enc` em falta não impede esta fase: usamos `x264enc` na CPU.
O launcher usa `/usr/bin/python3`, que encontra os bindings `gi` do apt.

## 2. Compilar a aplicação Android

Abre `android/` no Android Studio e deixa sincronizar o Gradle. Usa JDK 17
e instala Android SDK Platform 35 pelo SDK Manager. Para compilar no terminal,
configura `ANDROID_HOME` ou `sdk.dir` em `android/local.properties` (ignorado pelo Git):

```bash
cd android
./gradlew assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
cd ..
```

O wrapper descarrega uma versão fixa e verifica o SHA-256 da distribuição.
A compilação inicial precisa de Internet. A app requer Android 11/API 30 ou
superior. Este protótipo destina-se a instalação local; não está preparado para
publicação na Play Store.

## 3. Ligar por USB

Ativa as opções de programador e a depuração USB no tablet. Liga um cabo com
transferência de dados e aceita a chave do computador no tablet desbloqueado.

```bash
adb devices -l
lsusb -t
./scripts/usb-connect.sh
./scripts/server.sh --width 960 --height 640 --fps 30 --bitrate 4000
```

Abre OpenPadDisplay. Deverás ver uma bola em movimento. Depois do primeiro teste,
pára com Ctrl+C e executa `./scripts/server.sh` para pedir 1920×1280 a 60 FPS.
Só depois experimenta `--fps 144`.

Depois de compilar o APK, podes instalar, abrir a app e iniciar o teste de
960×640 a 30 FPS com um único comando na raiz do repositório:

```bash
./scripts/test-usb.sh
```

Este atalho seleciona um único dispositivo USB. Aceita também os argumentos
do servidor, por exemplo `./scripts/test-usb.sh --width 1920 --height 1280 --fps 60`.

Se o Xiaomi bloquear `adb install` com `INSTALL_FAILED_USER_RESTRICTED`, copia o
APK para o tablet e instala-o pelo gestor de ficheiros:

```bash
adb -d push android/app/build/outputs/apk/debug/app-debug.apk /sdcard/Download/000-OpenPadDisplay.apk
```

No tablet, abre Armazenamento interno → Download → `000-OpenPadDisplay.apk` → Instalar.
O prefixo `000-` coloca o APK no início da lista quando está ordenada por nome.
Depois inicia o teste sem repetir a instalação por ADB:

```bash
./scripts/test-usb.sh --skip-install
```

O servidor mostra FPS codificados/enviados. A app mostra FPS recebidos,
callbacks de apresentação e frequência reportada do painel. São indicadores
distintos; os callbacks não comprovam, por si só, 144 imagens diferentes no painel.
Ainda não existe medição de latência ponta a ponta.

Para vários dispositivos usa `./scripts/usb-connect.sh -s SERIAL` e
`adb -s SERIAL install -r android/app/build/outputs/apk/debug/app-debug.apk`.
Se mudares a porta do servidor, mantém a porta Android 27183:
`adb reverse tcp:27183 tcp:PORTA_DO_SERVIDOR`.

## Problemas comuns

| Sintoma | Ação |
|---|---|
| `adb: command not found` | Instalar `adb` com apt |
| `unauthorized` | Desbloquear o tablet e aceitar a autorização USB |
| `no permissions` no ADB | Verificar regras udev; não executar o servidor como root |
| App tenta ligar repetidamente | Confirmar servidor ativo, `adb devices` e repetir `usb-connect.sh` |
| Cabo desligado/religado | Recriar `adb reverse`; a app volta a tentar automaticamente |
| `No module named gi` | Usar o launcher com `/usr/bin/python3` |
| Elemento `x264enc` em falta | Instalar `gstreamer1.0-plugins-ugly` |
| Modo não suportado pelo descodificador | Reduzir resolução/FPS no servidor |
| FPS baixos ou aquecimento | Começar por 960×640 a 30 FPS; a codificação usa CPU |
| Painel fica a 60/120 Hz | Verificar HyperOS/poupança de energia; a app não força a frequência |
| `Address already in use` | Parar o outro servidor ou usar `--port` e ajustar `adb reverse` |

Uma ligação `5000M` em `lsusb -t` é desejável para os testes de maior débito,
mas não garante FPS. Um cabo USB 2 pode servir para o primeiro teste comprimido.
Nenhuma atualização do Ubuntu/GNOME é necessária nesta fase.

## 4. Usar como segundo monitor

Com o tablet autorizado e a aplicação instalada:

```bash
./scripts/extend-usb.sh
```

O atalho abre a app, refaz o túnel ADB e inicia um monitor virtual de 1920×1280
a uma frequência pedida de 60 Hz. Também podes configurar o modo:

```bash
./scripts/extend-usb.sh --width 960 --height 640 --fps 60 --bitrate 4000
```

No teste local, o GNOME colocou o ecrã adicional à direita do portátil. Arrasta
uma janela para fora da margem direita para a veres no tablet. Usa o rato e
o teclado do computador; o retorno de toque/caneta ainda não está implementado.
Consulta Definições → Ecrãs no Ubuntu para ver a disposição e o monitor `Meta-0`
(o nome pode variar). Não alteres a resolução nas definições do GNOME durante
a sessão: para mudar de modo, pára o servidor e ajusta os argumentos do comando.

Mantém a app em primeiro plano. Se a fechares ou desligares o cabo, o servidor
remove o monitor virtual e o GNOME traz as janelas de volta para os ecrãs restantes.
Ctrl+C no terminal também remove o monitor. Depois de voltar a ligar o cabo,
executa novamente o atalho para refazer o túnel USB.

O GNOME 46 foi verificado a negociar monitores virtuais de 960×640 a 60 Hz e
a 144 Hz através do PipeWire. Isto corrige a hipótese inicial de que seria
obrigatório atualizar o ambiente gráfico. Os 144 frames distintos apresentados
por segundo continuam a exigir testes de desempenho da cadeia completa.

Num ambiente de trabalho parado, o valor de FPS pode baixar: a captura reage a
alterações e mantém a ligação viva com repetições periódicas. Para avaliar fluidez,
move uma janela ou reproduz uma animação no ecrã do tablet. FPS em repouso não
representa a capacidade máxima do sistema.
