# Diagnóstico da ligação ao tablet

O painel de diagnóstico ajuda a comparar as etapas da ligação e orienta a
investigação de quebras de fluidez. Uma indicação de possível gargalo é uma
hipótese baseada nas amostras disponíveis, não uma medição de latência total.

## Abrir o painel

O APK **0.4.1** mostra apenas o vídeo por defeito. Na aplicação **do computador**,
liga o tablet e clica em **Mostrar métricas no tablet**. Aparecem só as métricas
sobre o vídeo, sem botões, caixas de confirmação nem controlos de teste no tablet.
Clica em **Ocultar métricas do tablet** para deixar a imagem completamente limpa.
A alteração é imediata e não reinicia a transmissão. Ao desligar, o launcher
oculta as métricas e repõe a opção desativada.

O launcher envia as métricas do host em v2 durante a sessão, mesmo com o painel
oculto. O botão controla apenas a visibilidade. O controlo usa a ligação ADB USB
já autorizada; falhas ou APKs antigos são indicados no computador, sem fingir que
a alteração foi aplicada. O estado selecionado é reaplicado após uma reconexão.

Os FPS locais, o decoder, o encoder anunciado e a frequência do painel também
estão disponíveis com servidores v1. Na linha de comandos, passa `--diagnostics`
ao servidor para enviar captura, envio e descartes do host. O protocolo v1
continua a ser o default da CLI; o novo APK aceita ambos os protocolos.

## O que significam as métricas

| Métrica | Interpretação |
| --- | --- |
| FPS pedidos | Objetivo da sessão; não é a taxa garantida. |
| FPS recebidos | Unidades H.264 entregues ao cliente por segundo. |
| Saídas do descodificador | Frames produzidos pelo MediaCodec, quando medidos. |
| Callbacks de apresentação | Notificações de frames renderizados na Surface. Podem chegar atrasadas ou agrupadas. |
| Frequência do painel | Modo de atualização escolhido pelo Android; não conta imagens distintas. |
| Encoder / decoder | Implementações efetivamente escolhidas para a sessão. |
| Captura do host | Buffers recebidos da fonte. Inclui repetições de manutenção num desktop parado. |
| Codificados/enviados | Frames H.264 codificados e entregues ao socket pelo host. |
| Descartes por cadência | Frames raw descartados por `videorate` antes da codificação; não são perdas USB. |
| Tempo máximo de envio | Maior tempo gasto numa escrita de frame no intervalo; exclui captura, codificação e tablet. |

TCP entrega os bytes por ordem ou termina a ligação com um erro. A diferença
entre contadores recebidos, descodificados e callbacks pode incluir frames em
trânsito, processamento pendente e atraso dos callbacks. Essa diferença, por si
só, não mede perdas na rede nem frames definitivamente perdidos.

A [documentação Android do callback de apresentação](https://developer.android.com/reference/android/media/MediaCodec.OnFrameRenderedListener)
explica que as notificações são informativas e podem chegar atrasadas ou
agrupadas. Em Android anterior ao 14, alguns frames renderizados podem nem
gerar callback. Não é possível provar a quantidade de imagens físicas distintas
ou a latência ponta a ponta só com estes contadores.

## Teste guiado: começar por uma fonte animada

1. Liga o tablet por USB na aplicação do computador.
2. Clica em **Testar ligação (15 s)** no computador e lê a indicação para manter
   uma janela em movimento. A confirmação e o cancelamento ficam no computador.
3. Mantém movimento no monitor do tablet. Os primeiros 3 segundos estabilizam a
   ligação; as amostras seguintes alimentam o resultado.
4. O resultado abre numa janela **no computador**. O tablet continua a mostrar
   apenas o vídeo e, se tiveres ativado o botão, as métricas.
5. Repete no modo que queres usar e muda apenas uma variável de cada vez:
   resolução, frequência, bitrate ou encoder.

Para comparar com uma fonte animada independente do desktop, encerra primeiro a
sessão do launcher e executa um servidor de teste, observando os logs:

```bash
./scripts/test-usb.sh --skip-install --diagnostics --encoder auto --pattern scroll --width 960 --height 640 --fps 60 --bitrate 4000
```

Termina com Ctrl+C antes de iniciar outra sessão. Os controlos do launcher são
ativados nas ligações iniciadas pelo próprio launcher.

O teste `scroll` separa a geração contínua da dependência das alterações do
desktop. No monitor estendido, move uma janela continuamente durante a recolha.
Uma imagem parada envia poucos frames por desenho e não demonstra um gargalo.
O teste pode ser cancelado e é interrompido ao perder/reiniciar a ligação ou
passar a aplicação para segundo plano. Uma recolha incompleta não produz um
diagnóstico de gargalo. As métricas e contadores recomeçam em cada sessão.

## Como investigar cada etapa

| Observação repetida com animação contínua | Próximo passo |
| --- | --- |
| Captura abaixo da cadência pedida, codificados acompanham captura | Comparar o desktop com `scroll` e baixar a resolução. Investigar fonte/captura; só esta observação não identifica a causa dentro do compositor. |
| Captura alta, menos frames codificados e fila raw sob pressão | Comparar NVENC com x264 e observar CPU. A pressão pode vir de codificação ou de uma etapa posterior. |
| Escritas do host demoradas e receção baixa no tablet | Baixar bitrate e observar a espera pelo decoder. O socket pode ficar bloqueado por contrapressão do cliente, por isso não atribuir logo ao cabo USB. |
| Receção acompanha o host, mas saídas do decoder ficam atrás | Repetir com menor resolução/frequência e verificar o decoder escolhido. Procurar espera na entrada e erros de codec. |
| Saídas do decoder acompanham a receção, mas callbacks ficam atrás | Observar vários intervalos e a frequência efetiva do painel. Atraso dos callbacks e composição Android precisam de análise adicional. |
| Falhas de sessão ou reconexões | Confirmar cabo, autorização, mapping ADB e mensagens de erro. Interrupções de sessão são diferentes de perdas raw e de frames pendentes. |

Para observar o cliente no terminal, sem apagar o histórico global:

```bash
adb logcat -s OpenPadDisplay:I
```

O benchmark `--benchmark` documentado em [desempenho](performance.md) mede apenas
o host. Serve para comparar capacidade de codificação, sem incluir USB,
descodificação ou apresentação no tablet.
