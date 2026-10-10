# wled-sketches

**English** · [Português](README.pt.md)

Two small Python programs that listen to a microphone and draw on a 15 x 10 [WLED](https://kno.wled.ge/) LED matrix over Wi-Fi.

- **`spectrum_wled`** draws a scrolling spectrogram: pitch runs left to right, time runs upwards, blue is quiet and green is loud.
- **`translate_wled`** listens for English, translates each phrase into Portuguese when you pause, and scrolls the translation across the panel. It can also go the other way, Portuguese to English. It runs entirely offline.

Both send frames to WLED as UDP realtime packets. When you stop a program with Ctrl-C, WLED returns to its own effect about two seconds later.

## What you need

| | |
|---|---|
| A WLED controller | Driving a 15 x 10 matrix, set up as a 2D matrix in WLED (Config → 2D Configuration), on the same network as your computer. |
| A Linux computer | With PulseAudio or PipeWire, which is what most desktop distributions use. The programs record through `parecord`. |
| A microphone | Whatever your system uses as its default input. |
| Python 3.9 or newer | |

`parecord` is part of `pulseaudio-utils`. If `parecord --version` prints nothing, install it:

```sh
sudo apt install pulseaudio-utils
```

The programs have only been run on Linux. macOS and Windows have no `parecord`, so they won't work there without changing how the microphone is read.

## Get the code

```sh
git clone https://github.com/MattChu/wled-sketches.git
cd wled-sketches
```

## Point it at your WLED

Both programs default to the address `10.10.10.161`, which is almost certainly not yours. Find your WLED's address in the WLED app or your router, then either pass it each time you run a program (shown below) or change `WLED_IP` near the top of each script.

In WLED, check that Config → Sync Interfaces → Realtime → "Receive UDP realtime" is ticked. It is by default.

## Spectrum

Nothing to install: it uses only the Python standard library.

```sh
python3 spectrum_wled/spectrum_wled.py 192.168.1.50
```

Leave the address off to use the one in the script. Settings such as the frequency range (`BANDS_HZ`), the scroll speed (`ROW_S`) and the colours (`QUIET`, `LOUD`) are constants near the top of the file.

## Translate

### Install

The translator needs three Python packages, which go in their own virtual environment:

```sh
python3 -m venv ~/.wled-translate-env
~/.wled-translate-env/bin/pip install -r translate_wled/requirements.txt
```

| Package | What it does |
|---|---|
| `vosk` | Recognises the speech |
| `ctranslate2` | Runs the translation model |
| `sentencepiece` | Splits text into the pieces the translation model expects |

### Run

```sh
python3 translate_wled/translate_wled.py --ip 192.168.1.50            # English to Portuguese
python3 translate_wled/translate_wled.py --ip 192.168.1.50 --to-en    # Portuguese to English
```

You can start it with any Python: it restarts itself with the one in `~/.wled-translate-env`.

The first run downloads the speech and translation models, about 280 MB, into `~/.cache/wled-translate`. After that it needs no internet connection.

Wait for it to print `listening`, then speak. A phrase is translated when you pause, and each one is also printed in the terminal next to what was heard, which is the easiest way to see whether a mistake came from the recognition or from the translation.

## If your matrix is different

- **Another size:** change `W` and `H` at the top of each script. The translator needs at least 5 rows.
- **The picture is scrambled:** the scripts send pixels row by row from the top left and rely on WLED's 2D configuration to match your wiring. If your panel is set up in WLED as a plain strip that zigzags, set `SERPENTINE = True` instead.
- **Nothing appears:** check the address, that the computer and the WLED are on the same network, and that "Receive UDP realtime" is on.
- **`parecord stopped`:** no microphone was found. Check your system's sound settings for a default input.

## Making the translation faster and more accurate

The translator makes its mistakes in two stages, and the terminal output shows you which one is at fault. If the heard text is wrong, work on the recognition. If the heard text is right but the translation is poor, work on the translation.

### Recognition

This is usually where most of the errors are.

1. **Use a better microphone, closer to your mouth.** A headset or a lapel microphone in a quiet room does more than any change of model.
2. **Use a larger Vosk model.** The script uses the small ones (about 40 MB) so that it starts quickly. The [Vosk model list](https://alphacephei.com/vosk/models) has larger ones, such as `vosk-model-en-us-0.22-lgraph` (128 MB) and `vosk-model-en-us-0.22` (1.8 GB) for English, and `vosk-model-pt-fb-v0.1.1-20220516_2113` (1.6 GB) for Portuguese. Change the addresses in `SPEECH_MODELS`. The largest ones need several GB of memory and take longer to load.
3. **Switch to Whisper.** [faster-whisper](https://github.com/SYSTRAN/faster-whisper) is noticeably more accurate than Vosk, and it adds punctuation and capitals, which the translation model was trained on and does better with. It runs on CTranslate2, which is already installed. Its `small` model is a good starting point on a laptop. The cost is that Whisper works on finished chunks of sound instead of a live stream, so `listen()` would need rewriting to cut the audio at pauses, and each phrase would take longer to appear unless you have a GPU.

### Translation

1. **Raise `beam_size`.** In `Translator.__call__` it is 2. Setting it to 4 or 5 makes the model consider more alternatives, for slightly better sentences and slightly more time. Setting it to 1 is the fastest.
2. **Use a larger translation model.** The Argos models are small and quick. [OPUS-MT](https://huggingface.co/Helsinki-NLP) models (for example `opus-mt-tc-big-en-pt`) and Meta's [NLLB-200](https://huggingface.co/facebook/nllb-200-distilled-600M) are better and can both be converted to run in CTranslate2 with its `ct2-transformers-converter` tool. They use a different tokeniser from the Argos models, so the `Translator` class needs adapting.
3. **Use an online service** if the panel doesn't have to work offline. DeepL and Google Translate are more accurate than anything that fits on a small computer, and both have Python libraries.

### Speed

Most of the wait is not computing: the program waits for you to pause before it translates anything.

1. **Translate before the pause.** Vosk gives its guess so far through `recogniser.PartialResult()`. Translating that as it grows would put words on the panel while you are still talking, at the price of words changing after they've appeared.
2. **Speak in short phrases.** A long sentence is translated all at once at the end.
3. **Quantise the translation model.** Add `compute_type="int8"` where `ctranslate2.Translator` is created. On a slow processor this roughly halves the translation time for very little loss.
4. **Use a GPU.** With an NVIDIA card and CUDA installed, change `device="cpu"` to `device="cuda"`. This matters far more with the larger models above than with the default ones.

If the panel falls behind your speech, it is the scrolling that is slow, not the translation: raise `SCROLL_PX_S`.

## Running the translator on a Raspberry Pi

This should work but has not been tried. All three packages publish builds for 64-bit ARM, and the default models are small enough for a Pi.

**Which Pi:** a Pi 4 or Pi 5 with 2 GB of memory or more, running 64-bit Raspberry Pi OS. A Pi Zero 2 W has 512 MB, which is probably too little for the speech and translation models together. A 32-bit system won't do, as CTranslate2 has no build for it.

**Microphone:** a Pi has no microphone input, so you need a USB microphone or a USB sound card.

**Install**, on Raspberry Pi OS with the desktop:

```sh
sudo apt update
sudo apt install git python3-venv pulseaudio-utils
git clone https://github.com/MattChu/wled-sketches.git
cd wled-sketches
python3 -m venv ~/.wled-translate-env
~/.wled-translate-env/bin/pip install -r translate_wled/requirements.txt
```

Plug in the microphone, check it is picked up, and run:

```sh
parecord --raw --rate=16000 --channels=1 test.raw    # speak, Ctrl-C, check test.raw isn't empty
python3 translate_wled/translate_wled.py --ip 192.168.1.50
```

Raspberry Pi OS Lite has no sound server running, so `parecord` has nothing to talk to. Install one as well:

```sh
sudo apt install pipewire pipewire-pulse wireplumber
```

**Start it when the Pi boots** by making it a user service. Save this as `~/.config/systemd/user/wled-translate.service`, with your own address:

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

Then:

```sh
systemctl --user daemon-reload
systemctl --user enable --now wled-translate
sudo loginctl enable-linger $USER    # so it starts without anyone logging in
journalctl --user -u wled-translate -f    # watch what it hears
```

Run it by hand once first, so the models are downloaded before the service needs them.

**On a Pi, expect** each phrase to take a little longer to appear than on a laptop. Stay with the small Vosk models, add `compute_type="int8"` as described above, and leave Whisper for a Pi 5.

The spectrum program does its maths in plain Python and may be too slow for a Pi at 30 frames a second. If the picture lags behind the sound, lower `FPS`.

## Licence

MIT. The models the translator downloads have their own licences: see [Vosk](https://alphacephei.com/vosk/models) and [Argos Translate](https://github.com/argosopentech/argos-translate).
