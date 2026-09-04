"""Derives a beat/hit grid from the music track for storyboard anchors.

Pipes mono PCM out of ffmpeg, computes spectral flux (Hann rFFT 1024 / hop 256),
estimates BPM by autocorrelating the flux over 60-200 BPM lags, picks the beat
phase as the comb-filter offset that maximises flux, and lists the loudest
onsets as hits. Nothing here is a tempo tracker: one global BPM, one offset.
Pass --bpm / --offset-ms / --tap to override the parts the estimate gets wrong.

Usage: uv run python video/capture/beat-grid.py public/music.mp3 [--out ...]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

SR = 22050
N_FFT = 1024
HOP = 256
MIN_BPM, MAX_BPM = 60.0, 200.0
HIT_SIGMA = 2.5
HIT_MIN_GAP_MS = 2000
DEFAULT_OUT = Path(__file__).resolve().parent.parent / "src" / "data" / "beat-grid.json"


def decode(path: Path) -> np.ndarray:
    cmd = ["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"]
    pcm = subprocess.run(cmd, check=True, capture_output=True).stdout
    return np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0


def spectral_flux(x: np.ndarray) -> np.ndarray:
    """Half-wave rectified magnitude flux per hop, normalised to unit peak."""
    n_frames = max(1, (len(x) - N_FFT) // HOP + 1)
    idx = np.arange(N_FFT)[None, :] + HOP * np.arange(n_frames)[:, None]
    frames = x[idx] * np.hanning(N_FFT)[None, :]
    mag = np.abs(np.fft.rfft(frames, axis=1))
    diff = np.diff(mag, axis=0, prepend=mag[:1])
    flux = np.maximum(diff, 0.0).sum(axis=1)
    return flux / (flux.max() or 1.0)


def frame_ms(i: float) -> float:
    return i * HOP * 1000.0 / SR


def estimate_bpm(flux: np.ndarray) -> float:
    f = flux - flux.mean()
    ac = np.correlate(f, f, mode="full")[len(f) - 1 :]
    lo = round(60.0 / MAX_BPM * SR / HOP)
    hi = round(60.0 / MIN_BPM * SR / HOP)
    best = lo + int(np.argmax(ac[lo : hi + 1]))
    # One hop is ~0.2 BPM at 100 BPM, so refine on the 8th multiple of the lag
    # (8x finer) with a parabolic fit around its peak.
    mult = 8 if best * 8 + 2 < len(ac) else 1
    lo8, hi8 = best * mult - mult, best * mult + mult
    k = lo8 + int(np.argmax(ac[lo8 : hi8 + 1]))
    y0, y1, y2 = ac[k - 1], ac[k], ac[k + 1]
    denom = y0 - 2 * y1 + y2
    lag = (k + (0.5 * (y0 - y2) / denom if denom else 0.0)) / mult
    return 60.0 * SR / (HOP * float(lag))


def estimate_offset_ms(flux: np.ndarray, bpm: float) -> float:
    period = 60.0 / bpm * SR / HOP
    n = int(np.ceil(period))
    scores = np.zeros(n)
    for phase in range(n):
        positions = np.arange(phase, len(flux), period)
        scores[phase] = flux[np.round(positions).astype(int).clip(0, len(flux) - 1)].sum()
    return frame_ms(int(np.argmax(scores)))


def beat_grid(duration_ms: float, bpm: float, offset_ms: float) -> list[int]:
    period_ms = 60000.0 / bpm
    first = offset_ms - period_ms * np.floor(offset_ms / period_ms)
    return [round(float(t)) for t in np.arange(first, duration_ms, period_ms)]


def hits(flux: np.ndarray) -> list[int]:
    """Flux peaks above mean + HIT_SIGMA sd; loudest first, each claiming a min gap."""
    threshold = flux.mean() + HIT_SIGMA * flux.std()
    peaks = np.flatnonzero((flux[1:-1] > flux[:-2]) & (flux[1:-1] >= flux[2:])) + 1
    peaks = peaks[flux[peaks] > threshold]
    out: list[int] = []
    for p in peaks[np.argsort(-flux[peaks], kind="stable")]:
        t = round(frame_ms(int(p)))
        if all(abs(t - h) >= HIT_MIN_GAP_MS for h in out):
            out.append(t)
    return sorted(out)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    p.add_argument("mp3", type=Path)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--bpm", type=float, help="override the estimated BPM")
    p.add_argument("--offset-ms", type=float, help="override the estimated beat phase")
    p.add_argument("--tap", help='hand-tapped hit times in seconds, "3.01,9.02,..."')
    p.add_argument("--source", default="", help="where the track came from, recorded in the JSON")
    p.add_argument("--trim-start-ms", type=int, default=0, help="in-point used when trimming")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    samples = decode(args.mp3)
    duration_ms = len(samples) * 1000.0 / SR
    flux = spectral_flux(samples)

    bpm = args.bpm if args.bpm else estimate_bpm(flux)
    offset_ms = args.offset_ms if args.offset_ms is not None else estimate_offset_ms(flux, bpm)
    beats = beat_grid(duration_ms, bpm, offset_ms)
    hit_list = (
        sorted(round(float(s) * 1000) for s in args.tap.split(",") if s.strip())
        if args.tap
        else hits(flux)
    )
    method = "+".join(
        [
            "bpm:" + ("arg" if args.bpm else "flux-autocorr"),
            "offset:" + ("arg" if args.offset_ms is not None else "comb-filter"),
            "hits:" + ("tap" if args.tap else f"flux>mean+{HIT_SIGMA}sd,gap>={HIT_MIN_GAP_MS}ms"),
        ]
    )

    grid = {
        "_comment": (
            "Generated by capture/beat-grid.py from public/music.mp3. Do not edit; re-run. "
            "Indices are what storyboard.json {beat:i}/{hit:i} anchors mean."
        ),
        "track": "public/music.mp3",
        "trackSha256": hashlib.sha256(args.mp3.read_bytes()).hexdigest(),
        "source": args.source,
        "trimStartMs": args.trim_start_ms,
        "durationMs": round(duration_ms),
        "bpm": round(bpm, 2),
        "beatOffsetMs": round(offset_ms),
        "method": method,
        "beatsMs": beats,
        "hitsMs": hit_list,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(grid, indent=2) + "\n")
    print(
        f"bpm={grid['bpm']} offset={grid['beatOffsetMs']}ms beats={len(beats)} "
        f"hits={len(hit_list)} first8={hit_list[:8]} -> {args.out}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
