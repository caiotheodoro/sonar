"""Synthesise the cut's sound effects into public/sfx/*.wav.

numpy only, seeded, 48 kHz mono 16-bit, every file under 500 ms with its
peak at -6 dBFS. The recipes are the whole design: no recordings, no
licences. Replace any file with a recording of the same name if you want
texture, and record its licence in docs/HANDOFF.md.

Usage: uv run python video/capture/sfx.py [--out video/public/sfx] [--if-missing]
"""

from __future__ import annotations

import argparse
import struct
import wave
from pathlib import Path

import numpy as np

SR = 48_000
PEAK = 10 ** (-6 / 20)
RNG = np.random.default_rng(20260904)


def t(ms: float) -> np.ndarray:
    return np.arange(int(SR * ms / 1000)) / SR


def env(n: int, attack_ms: float, decay_ms: float) -> np.ndarray:
    a = max(1, int(SR * attack_ms / 1000))
    d = max(1, int(SR * decay_ms / 1000))
    e = np.ones(n)
    e[:a] = np.linspace(0, 1, a)
    tail = np.exp(-np.arange(n - a) / d)
    e[a:] = tail[: n - a]
    return e


def noise(ms: float) -> np.ndarray:
    return RNG.standard_normal(int(SR * ms / 1000))


def bandpass(x: np.ndarray, lo: float, hi: float) -> np.ndarray:
    spec = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    spec[(f < lo) | (f > hi)] = 0
    return np.fft.irfft(spec, n=len(x))


def sine(ms: float, f0: float, f1: float | None = None) -> np.ndarray:
    tt = t(ms)
    f = np.linspace(f0, f1 if f1 is not None else f0, len(tt))
    return np.sin(2 * np.pi * np.cumsum(f) / SR)


def normalise(x: np.ndarray) -> np.ndarray:
    m = np.max(np.abs(x)) or 1.0
    return x / m * PEAK


def tick() -> np.ndarray:
    x = bandpass(noise(30), 4000, 8000) * env(int(SR * 0.03), 0.3, 6)
    return x


def key() -> np.ndarray:
    n = bandpass(noise(40), 200, 3500) * env(int(SR * 0.04), 0.5, 9)
    thock = sine(40, 180, 120) * env(int(SR * 0.04), 0.5, 12) * 0.6
    return n + thock


def shutter() -> np.ndarray:
    out = np.zeros(int(SR * 0.12))
    for at_ms in (0, 25):
        b = bandpass(noise(40), 2000, 6000) * env(int(SR * 0.04), 0.3, 7)
        i = int(SR * at_ms / 1000)
        out[i : i + len(b)] += b
    thump = sine(80, 60, 45) * env(int(SR * 0.08), 1, 25) * 0.7
    out[: len(thump)] += thump
    return out


def click() -> np.ndarray:
    imp = np.zeros(int(SR * 0.03))
    imp[:48] = np.linspace(1, 0, 48)
    ring = sine(30, 1200) * env(int(SR * 0.03), 0.2, 5) * 0.5
    return imp + ring


def blip() -> np.ndarray:
    return sine(50, 880, 1100) * env(int(SR * 0.05), 2, 14)


def sweep() -> np.ndarray:
    n = noise(250)
    spec = np.fft.rfft(n)
    f = np.fft.rfftfreq(len(n), 1 / SR)
    spec[(f < 400) | (f > 6000)] = 0
    x = np.fft.irfft(spec, n=len(n))
    # rising: modulate with a chirp so the perceived pitch climbs
    x = x * (0.5 + 0.5 * sine(250, 400, 6000))
    return x * env(len(x), 30, 90)


def whoosh() -> np.ndarray:
    n = noise(350)
    x = bandpass(n, 300, 5000) * (0.5 + 0.5 * sine(350, 3000, 200))
    return x * env(len(x), 60, 110)


def hit() -> np.ndarray:
    thump = sine(300, 55, 40) * env(int(SR * 0.3), 1, 110)
    crack = bandpass(noise(60), 1500, 9000) * env(int(SR * 0.06), 0.2, 8) * 0.8
    out = np.zeros(len(thump))
    out += thump
    out[: len(crack)] += crack
    for k in range(3):
        g = bandpass(noise(20), 800, 6000) * env(int(SR * 0.02), 0.2, 5) * 0.5
        i = int(SR * (0.09 + 0.045 * k))
        out[i : i + len(g)] += g
    return out


def stamp() -> np.ndarray:
    thud = sine(160, 90, 60) * env(int(SR * 0.16), 1, 45)
    wood = bandpass(noise(40), 600, 2500) * env(int(SR * 0.04), 0.3, 9) * 0.7
    out = np.zeros(len(thud))
    out += thud
    out[: len(wood)] += wood
    return out


def chime() -> np.ndarray:
    a = sine(400, 440) * env(int(SR * 0.4), 12, 140)
    e = sine(400, 659.25) * env(int(SR * 0.4), 12, 160)
    out = np.zeros(int(SR * 0.4))
    out += a * 0.7
    i = int(SR * 0.12)
    out[i:] += e[: len(out) - i]
    return out


RECIPES = {
    "tick": tick,
    "key": key,
    "shutter": shutter,
    "click": click,
    "blip": blip,
    "sweep": sweep,
    "whoosh": whoosh,
    "hit": hit,
    "stamp": stamp,
    "chime": chime,
}


def write(path: Path, x: np.ndarray) -> None:
    x = normalise(x)
    data = (np.clip(x, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data.tobytes())


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[1] / "public" / "sfx")
    p.add_argument("--if-missing", action="store_true")
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    made = []
    for name, fn in RECIPES.items():
        path = a.out / f"{name}.wav"
        if a.if_missing and path.exists():
            continue
        x = fn()
        assert len(x) <= SR * 0.5, name
        write(path, x)
        made.append(f"{name} {len(x) / SR * 1000:.0f}ms")
    print(", ".join(made) if made else "sfx: all present")


if __name__ == "__main__":
    main()
