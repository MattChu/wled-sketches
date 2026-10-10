#!/usr/bin/env python3
"""A scrolling spectrogram on a 15 x 10 WLED matrix, from the microphone.

The spectrum, BANDS_HZ low to high, is split into 15 bands spaced evenly in
pitch (log frequency), one per column. Each row is a moment: the bottom row
is now, coloured by how loud each band is, blue (quiet) to green (loudest);
every ROW_S it moves up a row, so the panel shows the last H * ROW_S
seconds. It adjusts to how loud it is: the loudest band lately is full
green, RANGE_DB below that is blue.

Microphone through parecord (PulseAudio / PipeWire), frames to WLED as UDP
realtime (DRGB) packets; plain Python, nothing to install:
    python3 spectrum_wled.py [ip]
Stop with Ctrl-C: WLED goes back to its own effect a couple of seconds later.
"""
import cmath
import math
import socket
import subprocess
import sys
import time

WLED_IP = "10.10.10.161"
PORT = 21324     # WLED's UDP realtime port
W, H = 15, 10
GAMMA = 2.2      # WLED doesn't gamma-correct realtime data
TIMEOUT_S = 2    # WLED goes back to its own effect this long after the last frame
SERPENTINE = False

RATE = 44100
FPS = 30
N = 2048                     # FFT size: 21.5 Hz per bin
BANDS_HZ = (80, 4000)        # voices (80 Hz up) and whistles (up to about 4 kHz)
# music has much more energy low down: lift each octave up by this much so
# the columns come out about level
TILT_DB_PER_OCTAVE = 3.0
RANGE_DB = 40                # blue is this far below full green
MIN_TOP_DB = -35             # full green is never below this (dB full scale), so silence stays blue
TOP_FALL_DB = 3.0            # full green settles back this much a second after something loud
ROW_S = 0.1                  # each row is this long: the rows move up this often

QUIET, LOUD = (0, 0, 255), (0, 255, 0)


def lerp(a, b, f):
    return tuple(x + (y - x) * f for x, y in zip(a, b))


def fft(x):
    """Radix-2 FFT of a list of complex numbers, length a power of two."""
    n = len(x)
    bits = n.bit_length() - 1
    a = [x[int(f"{i:0{bits}b}"[::-1], 2)] for i in range(n)]
    size = 2
    while size <= n:
        w_step = cmath.exp(-2j * math.pi / size)
        half = size // 2
        for start in range(0, n, size):
            w = 1
            for k in range(start, start + half):
                t = w * a[k + half]
                a[k + half] = a[k] - t
                a[k] += t
                w *= w_step
        size *= 2
    return a


WINDOW = [0.5 - 0.5 * math.cos(2 * math.pi * i / N) for i in range(N)]
# so a full-scale sine comes out at 0 dB
NORM = 4 / sum(WINDOW) ** 2
# each column's FFT bins: 16 edges spaced evenly in pitch, at least one bin a band
EDGES = [BANDS_HZ[0] * (BANDS_HZ[1] / BANDS_HZ[0]) ** (i / W) for i in range(W + 1)]
BINS = []
for lo, hi in zip(EDGES, EDGES[1:]):
    a = round(lo * N / RATE)
    BINS.append(range(a, max(a + 1, round(hi * N / RATE))))
TILT = [TILT_DB_PER_OCTAVE * math.log2(math.sqrt(lo * hi) / BANDS_HZ[0])
        for lo, hi in zip(EDGES, EDGES[1:])]


def band_levels(samples):
    """Each column's loudness in dB (full scale), tilted, from N samples -1..1."""
    spectrum = fft([s * w for s, w in zip(samples, WINDOW)])
    levels = []
    for col, bins in enumerate(BINS):
        power = sum(abs(spectrum[b]) ** 2 for b in bins) * NORM
        levels.append(10 * math.log10(power + 1e-12) + TILT[col])
    return levels


def frame(rows):
    """rows: H lists of W loudnesses 0-1, top (oldest) first."""
    out = bytearray()
    for y in range(H):
        row = [lerp(QUIET, LOUD, f) for f in rows[y]]
        if SERPENTINE and y % 2:
            row.reverse()
        for c in row:
            for v in c:
                out.append(round(255 * (min(max(v, 0), 255) / 255) ** GAMMA))
    return out


def main():
    ip = sys.argv[1] if len(sys.argv) > 1 else WLED_IP
    hop = RATE // FPS
    mic = subprocess.Popen(["parecord", "--raw", "--format=s16le", f"--rate={RATE}",
                            "--channels=1", f"--latency-msec={1000 // FPS}"],
                           stdout=subprocess.PIPE)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    samples = [0.0] * N
    top = MIN_TOP_DB
    rows = [[0.0] * W for _ in range(H)]
    row_start = time.time()
    dt = 1 / FPS
    print(f"microphone -> {ip}:{PORT}, Ctrl-C to stop")
    try:
        while True:
            # reading the next hop of sound paces the loop at FPS
            raw = mic.stdout.read(hop * 2)
            if len(raw) < hop * 2:
                sys.exit("parecord stopped")
            samples = samples[hop:] + [int.from_bytes(raw[i:i + 2], "little", signed=True) / 32768
                                       for i in range(0, len(raw), 2)]
            levels = band_levels(samples)

            top = max(MIN_TOP_DB, top - TOP_FALL_DB * dt, max(levels))
            now = time.time()
            if now - row_start >= ROW_S:
                # this moment's row moves up, and a new one starts at the bottom
                rows = rows[1:] + [[0.0] * W]
                row_start = now
            # the bottom row holds the loudest each band has been during its moment
            for x, level in enumerate(levels):
                f = min(max((level - (top - RANGE_DB)) / RANGE_DB, 0), 1)
                rows[-1][x] = max(rows[-1][x], f)
            sock.sendto(bytes([2, TIMEOUT_S]) + frame(rows), (ip, PORT))
    except KeyboardInterrupt:
        pass
    finally:
        mic.terminate()


if __name__ == "__main__":
    main()
