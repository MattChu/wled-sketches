#!/usr/bin/env python3
"""Speech, translated, scrolling across a 15 x 10 WLED matrix.

Listens to the microphone for English and translates each phrase into
Portuguese as you pause. The translation scrolls across the middle of the
panel in 5-pixel capitals (5 rows has no room for accents: AÇÃO shows as
ACAO). With --to-en it listens for Portuguese and shows English. It all runs offline:
Vosk recognises the speech, an Argos Translate model (through CTranslate2)
translates it.

Setup, once (in its own venv):
    python3 -m venv ~/.wled-translate-env
    ~/.wled-translate-env/bin/pip install -r requirements.txt
The models (about 280 MB) are downloaded into MODEL_DIR the first time.
Then:
    python3 translate_wled.py [--to-en] [--ip IP]
(it runs itself with the venv's Python when it isn't started with it).
Stop with Ctrl-C: WLED goes back to its own effect a couple of seconds later.
"""
import argparse
import importlib.util
import json
import os
import queue
import socket
import subprocess
import sys
import threading
import time
import unicodedata
import urllib.request
import zipfile

WLED_IP = "10.10.10.161"
PORT = 21324     # WLED's UDP realtime port
W, H = 15, 10
FPS = 30
GAMMA = 2.2      # WLED doesn't gamma-correct realtime data
TIMEOUT_S = 2    # WLED goes back to its own effect this long after the last frame
SERPENTINE = False

COLOUR = (255, 150, 30)
LINE_H = 5
TOP = (H - LINE_H) // 2      # the panel row the line of text starts on
SCROLL_PX_S = 18.0          # columns a second (about 6 letters)
# if it falls behind the speech, it speeds up so the newest words are never
# more than about this many seconds away
MAX_LAG_S = 8.0
PHRASE_GAP = 6               # blank columns between phrases
# the small English model hears "the" or "huh" in background noise
IGNORE = {"", "the", "huh"}

MODEL_DIR = os.path.expanduser("~/.cache/wled-translate")
SPEECH_MODELS = {
    "en": "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip",
    "pt": "https://alphacephei.com/vosk/models/vosk-model-small-pt-0.3.zip",
}
TRANSLATION_MODELS = {
    ("en", "pt"): "https://argos-net.com/v1/translate-en_pt-1_9.argosmodel",
    ("pt", "en"): "https://argos-net.com/v1/translate-pt_en-1_9.argosmodel",
}
RATE = 16000     # what the Vosk models expect
VENV_PYTHON = os.path.expanduser("~/.wled-translate-env/bin/python")

# --- the font: 5 rows high, capitals; '#' lit. Glyphs are trimmed to their
# lit columns (a space is 2 wide), with a blank column between letters ---
FONT = {
    "A": ".#. #.# ### #.# #.#",
    "B": "##. #.# ##. #.# ##.",
    "C": ".## #.. #.. #.. .##",
    "D": "##. #.# #.# #.# ##.",
    "E": "### #.. ##. #.. ###",
    "F": "### #.. ##. #.. #..",
    "G": ".## #.. #.# #.# .##",
    "H": "#.# #.# ### #.# #.#",
    "I": "### .#. .#. .#. ###",
    "J": "..# ..# ..# #.# .#.",
    "K": "#.# #.# ##. #.# #.#",
    "L": "#.. #.. #.. #.. ###",
    "M": "#...# ##.## #.#.# #...# #...#",
    "N": "#..# ##.# #.## #..# #..#",
    "O": ".#. #.# #.# #.# .#.",
    "P": "##. #.# ##. #.. #..",
    "Q": ".#. #.# #.# #.# .##",
    "R": "##. #.# ##. #.# #.#",
    "S": ".## #.. .#. ..# ##.",
    "T": "### .#. .#. .#. .#.",
    "U": "#.# #.# #.# #.# ###",
    "V": "#.# #.# #.# #.# .#.",
    "W": "#...# #...# #.#.# #.#.# .#.#.",
    "X": "#.# #.# .#. #.# #.#",
    "Y": "#.# #.# .#. .#. .#.",
    "Z": "### ..# .#. #.. ###",
    "0": "### #.# #.# #.# ###",
    "1": ".#. ##. .#. .#. ###",
    "2": "##. ..# .#. #.. ###",
    "3": "##. ..# .#. ..# ##.",
    "4": "#.# #.# ### ..# ..#",
    "5": "### #.. ##. ..# ##.",
    "6": ".## #.. ### #.# ###",
    "7": "### ..# .#. .#. .#.",
    "8": "### #.# ### #.# ###",
    "9": "### #.# ### ..# ##.",
    ".": ". . . . #",
    ",": ". . . # #",
    "!": "# # # . #",
    "?": "##. ..# .#. ... .#.",
    "'": "# # . . .",
    "-": "... ... ### ... ...",
    ":": ". # . # .",
}


def glyph_columns(ch):
    """A character's columns, each LINE_H booleans; accents are dropped."""
    base = unicodedata.normalize("NFD", ch.upper())[0]
    if base not in FONT:
        return [[False] * LINE_H for _ in range(2)]
    rows = FONT[base].split()
    lit = [x for x in range(len(rows[0])) if any(r[x] == "#" for r in rows)]
    return [[r[x] == "#" for r in rows] for x in range(lit[0], lit[-1] + 1)]


def text_columns(text):
    out = []
    for ch in text:
        out += glyph_columns(ch) + [[False] * LINE_H]
    return out


def fetch(url, dest):
    """Download and unzip a model into MODEL_DIR, unless it's there already."""
    if os.path.isdir(dest):
        return dest
    os.makedirs(MODEL_DIR, exist_ok=True)
    print(f"downloading {url}")
    archive = dest + ".zip"
    urllib.request.urlretrieve(url, archive)
    with zipfile.ZipFile(archive) as z:
        z.extractall(MODEL_DIR)
    os.remove(archive)
    return dest


def model_path(url):
    name = url.rsplit("/", 1)[1].rsplit(".", 1)[0]
    return fetch(url, os.path.join(MODEL_DIR, name))


class Translator:
    def __init__(self, source, target):
        import ctranslate2
        import sentencepiece
        path = model_path(TRANSLATION_MODELS[(source, target)])
        self.model = ctranslate2.Translator(os.path.join(path, "model"), device="cpu")
        self.pieces = sentencepiece.SentencePieceProcessor(
            model_file=os.path.join(path, "sentencepiece.model"))

    def __call__(self, text):
        out = self.model.translate_batch([self.pieces.encode(text, out_type=str)], beam_size=2)
        return "".join(out[0].hypotheses[0]).replace("▁", " ").strip()


def listen(source, target, phrases):
    """Recognise speech from the microphone, phrase by phrase, and put each
    one's translation on phrases (runs in its own thread)."""
    import vosk
    vosk.SetLogLevel(-1)
    recogniser = vosk.KaldiRecognizer(vosk.Model(model_path(SPEECH_MODELS[source])), RATE)
    translate = Translator(source, target)
    mic = subprocess.Popen(["parecord", "--raw", "--format=s16le", f"--rate={RATE}",
                            "--channels=1", "--latency-msec=100"], stdout=subprocess.PIPE)
    print("listening")
    try:
        while True:
            data = mic.stdout.read(RATE // 5 * 2)
            if not data:
                print("parecord stopped")
                return
            if not recogniser.AcceptWaveform(data):
                continue
            heard = json.loads(recogniser.Result())["text"].strip()
            if heard in IGNORE:
                continue
            said = translate(heard)
            print(f"{heard}  ->  {said}")
            phrases.put(said)
    finally:
        mic.terminate()


def main():
    # started with another Python (python3, an editor's Run button): restart
    # with the venv's, which has Vosk
    if importlib.util.find_spec("vosk") is None and os.path.exists(VENV_PYTHON):
        os.execv(VENV_PYTHON, [VENV_PYTHON, os.path.abspath(__file__)] + sys.argv[1:])
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--to-en", action="store_true",
                   help="listen for Portuguese and show English (default: English to Portuguese)")
    p.add_argument("--ip", default=WLED_IP, help=f"the WLED's address (default: {WLED_IP})")
    args = p.parse_args()
    source, target = ("pt", "en") if args.to_en else ("en", "pt")

    phrases = queue.Queue()
    listener = threading.Thread(target=listen, args=(source, target, phrases), daemon=True)
    listener.start()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # the text scrolls along a tape of columns: the panel shows tape[pos:pos + W]
    tape = []
    pos = 0.0
    last = time.time()
    try:
        while True:
            if not listener.is_alive():
                sys.exit("stopped listening")
            now = time.time()
            dt, last = now - last, now
            while not phrases.empty():
                # a new phrase starts off the right edge, after a gap
                gap = max(PHRASE_GAP, int(pos) + W - len(tape))
                tape += [[False] * LINE_H for _ in range(gap)] + text_columns(phrases.get())
            if pos < len(tape):
                backlog = len(tape) - pos - W
                pos = min(len(tape), pos + max(SCROLL_PX_S, backlog / MAX_LAG_S) * dt)
            # forget what has scrolled off
            if pos > 100:
                tape, pos = tape[int(pos):], pos - int(pos)

            start = int(pos)
            shown = tape[start:start + W] + [[False] * LINE_H] * (W - len(tape[start:start + W]))
            out = bytearray([2, TIMEOUT_S])
            for y in range(H):
                lit = TOP <= y < TOP + LINE_H
                row = [COLOUR if lit and col[y - TOP] else (0, 0, 0) for col in shown]
                if SERPENTINE and y % 2:
                    row.reverse()
                for c in row:
                    out += bytes(round(255 * (v / 255) ** GAMMA) for v in c)
            sock.sendto(out, (args.ip, PORT))
            time.sleep(max(0.0, 1 / FPS - (time.time() - now)))
    except KeyboardInterrupt:
        pass
    sys.exit()


if __name__ == "__main__":
    main()
