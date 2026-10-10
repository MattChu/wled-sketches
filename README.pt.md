# wled-sketches

[English](README.md) · **Português**

Dois pequenos programas em Python que ouvem o microfone e desenham em uma matriz de LEDs [WLED](https://kno.wled.ge/) de 15 x 10 pelo Wi-Fi.

- **`spectrum_wled`** desenha um espectrograma que rola: o tom vai da esquerda para a direita, o tempo sobe, azul é silêncio e verde é som alto.
- **`translate_wled`** ouve inglês, traduz cada frase para português quando você faz uma pausa e passa a tradução pelo painel. Também funciona no sentido contrário, de português para inglês. Roda totalmente offline.

Os dois enviam os quadros para o WLED como pacotes UDP em tempo real. Quando você para um programa com Ctrl-C, o WLED volta ao seu próprio efeito uns dois segundos depois.

## O que você precisa

| | |
|---|---|
| Um controlador WLED | Ligado a uma matriz de 15 x 10, configurada como matriz 2D no WLED (Config → 2D Configuration), na mesma rede do seu computador. |
| Um computador com Linux | Com PulseAudio ou PipeWire, que é o que a maioria das distribuições de desktop usa. Os programas gravam pelo `parecord`. |
| Um microfone | O que o seu sistema usa como entrada padrão. |
| Python 3.9 ou mais recente | |

O `parecord` faz parte do `pulseaudio-utils`. Se `parecord --version` não mostrar nada, instale:

```sh
sudo apt install pulseaudio-utils
```

Os programas só foram testados no Linux. macOS e Windows não têm `parecord`, então não vão funcionar neles sem mudar a forma de ler o microfone.

## Baixe o código

```sh
git clone https://github.com/MattChu/wled-sketches.git
cd wled-sketches
```

## Aponte para o seu WLED

Os dois programas usam por padrão o endereço `10.10.10.161`, que quase com certeza não é o seu. Descubra o endereço do seu WLED no aplicativo do WLED ou no roteador e então passe o endereço cada vez que rodar um programa (como mostrado abaixo) ou mude `WLED_IP` perto do início de cada script.

No WLED, confira se Config → Sync Interfaces → Realtime → "Receive UDP realtime" está marcado. Vem marcado por padrão.

## Spectrum

Nada para instalar: usa só a biblioteca padrão do Python.

```sh
python3 spectrum_wled/spectrum_wled.py 192.168.1.50
```

Sem o endereço, ele usa o que está no script. Ajustes como a faixa de frequências (`BANDS_HZ`), a velocidade de rolagem (`ROW_S`) e as cores (`QUIET`, `LOUD`) são constantes perto do início do arquivo.

## Translate

### Instalação

O tradutor precisa de três pacotes Python, que ficam em um ambiente virtual próprio:

```sh
python3 -m venv ~/.wled-translate-env
~/.wled-translate-env/bin/pip install -r translate_wled/requirements.txt
```

| Pacote | O que faz |
|---|---|
| `vosk` | Reconhece a fala |
| `ctranslate2` | Roda o modelo de tradução |
| `sentencepiece` | Divide o texto nos pedaços que o modelo de tradução espera |

### Como rodar

```sh
python3 translate_wled/translate_wled.py --ip 192.168.1.50            # inglês para português
python3 translate_wled/translate_wled.py --ip 192.168.1.50 --to-en    # português para inglês
```

Você pode iniciá-lo com qualquer Python: ele se reinicia com o que está em `~/.wled-translate-env`.

Na primeira vez ele baixa os modelos de fala e de tradução, cerca de 280 MB, para `~/.cache/wled-translate`. Depois disso não precisa de internet.

Espere aparecer `listening` e então fale. Cada frase é traduzida quando você faz uma pausa e também é mostrada no terminal ao lado do que foi ouvido, que é o jeito mais fácil de ver se um erro veio do reconhecimento ou da tradução.

A fonte do painel tem 5 pixels de altura e só maiúsculas, então os acentos são removidos: AÇÃO aparece como ACAO.

## Se a sua matriz for diferente

- **Outro tamanho:** mude `W` e `H` no início de cada script. O tradutor precisa de pelo menos 5 linhas.
- **A imagem aparece embaralhada:** os scripts enviam os pixels linha por linha a partir do canto superior esquerdo e contam com a configuração 2D do WLED para corresponder à sua fiação. Se o seu painel estiver configurado no WLED como uma fita simples em ziguezague, use `SERPENTINE = True`.
- **Não aparece nada:** confira o endereço, se o computador e o WLED estão na mesma rede e se "Receive UDP realtime" está ligado.
- **`parecord stopped`:** nenhum microfone foi encontrado. Veja nas configurações de som do sistema se há uma entrada padrão.

## Como deixar a tradução mais rápida e mais precisa

O tradutor erra em duas etapas, e o terminal mostra qual delas falhou. Se o texto ouvido está errado, melhore o reconhecimento. Se o texto ouvido está certo mas a tradução é ruim, melhore a tradução.

### Reconhecimento

Normalmente é aqui que está a maior parte dos erros.

1. **Use um microfone melhor, mais perto da boca.** Um headset ou um microfone de lapela em um lugar silencioso ajuda mais do que qualquer troca de modelo.
2. **Use um modelo Vosk maior.** O script usa os pequenos (cerca de 40 MB) para iniciar rápido. A [lista de modelos do Vosk](https://alphacephei.com/vosk/models) tem modelos maiores, como `vosk-model-en-us-0.22-lgraph` (128 MB) e `vosk-model-en-us-0.22` (1,8 GB) para inglês, e `vosk-model-pt-fb-v0.1.1-20220516_2113` (1,6 GB) para português. Mude os endereços em `SPEECH_MODELS`. Os maiores precisam de vários GB de memória e demoram mais para carregar.
3. **Troque para o Whisper.** O [faster-whisper](https://github.com/SYSTRAN/faster-whisper) é visivelmente mais preciso que o Vosk e coloca pontuação e maiúsculas, com as quais o modelo de tradução foi treinado e funciona melhor. Ele roda no CTranslate2, que já está instalado. O modelo `small` é um bom começo em um notebook. O custo é que o Whisper trabalha com trechos de som já terminados, e não com um fluxo ao vivo, então `listen()` precisaria ser reescrita para cortar o áudio nas pausas, e cada frase demoraria mais para aparecer, a não ser que você tenha uma GPU.

### Tradução

1. **Aumente `beam_size`.** Em `Translator.__call__` o valor é 2. Com 4 ou 5 o modelo considera mais alternativas: frases um pouco melhores e um pouco mais de tempo. Com 1 é o mais rápido.
2. **Use um modelo de tradução maior.** Os modelos do Argos são pequenos e rápidos. Os modelos [OPUS-MT](https://huggingface.co/Helsinki-NLP) (por exemplo `opus-mt-tc-big-en-pt`) e o [NLLB-200](https://huggingface.co/facebook/nllb-200-distilled-600M) da Meta são melhores, e ambos podem ser convertidos para rodar no CTranslate2 com a ferramenta `ct2-transformers-converter`. Eles usam um tokenizador diferente do dos modelos do Argos, então a classe `Translator` precisa ser adaptada.
3. **Use um serviço online**, se o painel não precisar funcionar offline. DeepL e Google Tradutor são mais precisos do que qualquer coisa que caiba em um computador pequeno, e os dois têm bibliotecas para Python.

### Velocidade

A maior parte da espera não é processamento: o programa espera você fazer uma pausa antes de traduzir.

1. **Traduza antes da pausa.** O Vosk dá o palpite até o momento por `recogniser.PartialResult()`. Traduzir isso enquanto cresce colocaria palavras no painel com você ainda falando, ao preço de as palavras mudarem depois de aparecer.
2. **Fale em frases curtas.** Uma frase longa é traduzida inteira de uma vez, no final.
3. **Quantize o modelo de tradução.** Acrescente `compute_type="int8"` onde `ctranslate2.Translator` é criado. Em um processador lento isso reduz o tempo de tradução mais ou menos pela metade, com muito pouca perda.
4. **Use uma GPU.** Com uma placa NVIDIA e CUDA instalado, mude `device="cpu"` para `device="cuda"`. Isso faz muito mais diferença com os modelos maiores acima do que com os padrão.

Se o painel ficar para trás em relação à sua fala, o lento é a rolagem, não a tradução: aumente `SCROLL_PX_S`.

## Como rodar o tradutor em um Raspberry Pi

Deve funcionar, mas não foi testado. Os três pacotes publicam versões para ARM de 64 bits, e os modelos padrão são pequenos o bastante para um Pi.

**Qual Pi:** um Pi 4 ou Pi 5 com 2 GB de memória ou mais, com o Raspberry Pi OS de 64 bits. Um Pi Zero 2 W tem 512 MB, o que provavelmente é pouco para os modelos de fala e de tradução juntos. Um sistema de 32 bits não serve, porque o CTranslate2 não tem versão para ele.

**Microfone:** o Pi não tem entrada de microfone, então você precisa de um microfone USB ou de uma placa de som USB.

**Instalação**, no Raspberry Pi OS com desktop:

```sh
sudo apt update
sudo apt install git python3-venv pulseaudio-utils
git clone https://github.com/MattChu/wled-sketches.git
cd wled-sketches
python3 -m venv ~/.wled-translate-env
~/.wled-translate-env/bin/pip install -r translate_wled/requirements.txt
```

Conecte o microfone, confira se ele foi reconhecido e rode:

```sh
parecord --raw --rate=16000 --channels=1 test.raw    # fale, Ctrl-C, veja se test.raw não está vazio
python3 translate_wled/translate_wled.py --ip 192.168.1.50
```

O Raspberry Pi OS Lite não tem servidor de som rodando, então o `parecord` não tem com quem falar. Instale um também:

```sh
sudo apt install pipewire pipewire-pulse wireplumber
```

**Para iniciar quando o Pi ligar**, transforme-o em um serviço de usuário. Salve isto como `~/.config/systemd/user/wled-translate.service`, com o seu endereço:

```ini
[Unit]
Description=Speech translation on the WLED matrix
After=pipewire-pulse.service network-online.target

[Service]
ExecStart=%h/.wled-translate-env/bin/python %h/wled-sketches/translate_wled/translate_wled.py --ip 192.168.1.50
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
```

Depois:

```sh
systemctl --user daemon-reload
systemctl --user enable --now wled-translate
sudo loginctl enable-linger $USER    # para iniciar sem ninguém fazer login
journalctl --user -u wled-translate -f    # veja o que ele ouve
```

Rode uma vez à mão antes, para que os modelos sejam baixados antes de o serviço precisar deles.

**Em um Pi, espere** que cada frase demore um pouco mais para aparecer do que em um notebook. Fique com os modelos pequenos do Vosk, acrescente `compute_type="int8"` como descrito acima e deixe o Whisper para um Pi 5.

O programa do espectro faz as contas em Python puro e pode ser lento demais para um Pi a 30 quadros por segundo. Se a imagem atrasar em relação ao som, diminua `FPS`.

## Licença

MIT. Os modelos que o tradutor baixa têm suas próprias licenças: veja [Vosk](https://alphacephei.com/vosk/models) e [Argos Translate](https://github.com/argosopentech/argos-translate).
