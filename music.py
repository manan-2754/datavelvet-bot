"""
Procedural soundtrack, cut to the edit: every video gets its own key, mode, tempo, chord progression and lead
instrument (from the video seed), and the music follows the scene structure - the chord changes exactly on every
scene cut, the groove restarts on the cut, the hook is sparse, the middle drives, the outro drops out and lands.
Mixed under the voice by audio_build.mix (ducked hard while words are spoken).
"""
import random

import numpy as np

MODES = {"minor": [0, 2, 3, 5, 7, 8, 10], "dorian": [0, 2, 3, 5, 7, 9, 10], "major": [0, 2, 4, 5, 7, 9, 11],
         "lydian": [0, 2, 4, 6, 7, 9, 11], "phrygian": [0, 1, 3, 5, 7, 8, 10]}
PROGS = [[0, 5, 2, 6], [0, 3, 5, 4], [0, 5, 3, 4], [5, 3, 0, 4], [0, 2, 5, 6], [0, 6, 5, 6], [0, 3, 6, 4], [3, 4, 0, 5]]
LEADS = ["pluck", "bell", "glass", "none"]
NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def _hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def _env(n, sr, a, d):
    t = np.arange(n) / sr
    return np.minimum(1, t / max(a, 1e-4)) * np.exp(-t / max(d, 1e-4))


def _add(buf, i, s):
    if i >= len(buf) or i < 0:
        return
    e = min(len(buf), i + len(s))
    buf[i:e] += s[: e - i]


def render(starts, total, sr, seed, hook_end=None, outro_start=None):
    """starts: scene start times (s); total: length (s). Returns (mono float32, description)."""
    rng = random.Random(seed)
    nrng = np.random.default_rng(seed)
    mode = rng.choice(list(MODES))
    scale = MODES[mode]
    root = rng.randint(43, 52)
    bpm = rng.choice([90, 96, 100, 104, 110, 116, 120, 124, 128])
    prog = rng.choice(PROGS)
    lead = rng.choice(LEADS)
    swing = rng.choice([0, 0, 0.08, 0.12])
    beat = 60.0 / bpm
    N = int(total * sr)
    pad, bass, drums, arp = (np.zeros(N, np.float32) for _ in range(4))
    starts = sorted(set([0.0] + [s for s in starts if 0 < s < total]))
    bounds = starts + [total]

    def chord(deg):
        return [root + 12 + scale[(deg + k) % 7] + 12 * ((deg + k) // 7) for k in (0, 2, 4)]

    for si, (a, b) in enumerate(zip(bounds, bounds[1:])):
        notes = chord(prog[si % len(prog)])
        i0, n = int(a * sr), int((b - a) * sr)
        if n <= 0:
            continue
        t = np.arange(n) / sr
        sparse = hook_end is not None and a < hook_end
        ending = outro_start is not None and a >= outro_start
        p = np.zeros(n, np.float32)
        for m in notes:
            for det in (-0.08, 0.08):
                f = _hz(m + det)
                for h, amp in ((1, 1.0), (2, 0.35), (3, 0.16)):
                    p += (amp * np.sin(2 * np.pi * f * h * t + rng.random() * 6.28)).astype(np.float32)
        fade = np.minimum(1, t / 0.35) * np.minimum(1, (n / sr - t) / 0.08 + 0.001)
        _add(pad, i0, (p * fade * 0.05).astype(np.float32))
        k = 0
        while True:
            tb = a + k * beat
            if tb >= b - 0.02:
                break
            ib = int(tb * sr)
            if not sparse and not ending:
                kn = int(0.32 * sr)
                tt = np.arange(kn) / sr
                f = 40 + 70 * np.exp(-tt * 28)
                _add(drums, ib, (np.sin(2 * np.pi * np.cumsum(f) / sr) * np.exp(-tt * 9) * (0.9 if k % 4 == 0 else 0.6)).astype(np.float32))
                hn = int(0.05 * sr)
                noise = np.diff(nrng.standard_normal(hn), prepend=0).astype(np.float32)
                _add(drums, int((tb + beat * (0.5 + swing)) * sr), noise * _env(hn, sr, 0.001, 0.012).astype(np.float32) * 0.18)
                bn = int(beat * 0.9 * sr)
                tt = np.arange(bn) / sr
                _add(bass, ib, (np.sin(2 * np.pi * _hz(notes[0] - 12) * tt) * _env(bn, sr, 0.01, beat * 0.6) * 0.32).astype(np.float32))
            if lead != "none" and not ending:
                steps = 2 if sparse else 4
                for q in range(steps):
                    tq = tb + q * beat / steps
                    if tq >= b - 0.02:
                        break
                    m = notes[(k * 4 + q) % 3] + 12 * (1 if (k + q) % 5 else 2)
                    ln = int(0.4 * sr)
                    tt = np.arange(ln) / sr
                    f = _hz(m)
                    if lead == "pluck":
                        s = (np.sin(2 * np.pi * f * tt) + 0.4 * np.sin(4 * np.pi * f * tt)) * _env(ln, sr, 0.002, 0.09)
                    elif lead == "bell":
                        s = (np.sin(2 * np.pi * f * tt) + 0.5 * np.sin(2 * np.pi * f * 2.76 * tt) * np.exp(-tt * 10)) * _env(ln, sr, 0.002, 0.25)
                    else:
                        s = (np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(2 * np.pi * f * 3.01 * tt)) * _env(ln, sr, 0.01, 0.18)
                    _add(arp, int(tq * sr), (s * 0.06).astype(np.float32))
            k += 1
    if outro_start is not None:
        ln = int(1.6 * sr)
        tt = np.arange(ln) / sr
        hit = sum(np.sin(2 * np.pi * _hz(m) * tt) for m in chord(prog[0])) * _env(ln, sr, 0.005, 0.6) * 0.12
        _add(pad, int(max(0, min(total - 1.6, outro_start + 1.0)) * sr), hit.astype(np.float32))
    out = pad + bass + drums + arp
    out /= max(1e-6, float(np.abs(out).max()))
    return (out * 0.5).astype(np.float32), f"{mode} in {NOTE_NAMES[root % 12]}, {bpm} bpm, lead {lead}"
