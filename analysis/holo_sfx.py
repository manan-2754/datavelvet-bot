"""Sound design for the holo-bot promo: places the kit's sound effects (audio/sfx) on the same word timings
the plates animate on, ducks them under the voice and writes out/mix.wav (48 kHz stereo).

    python analysis/holo_sfx.py
"""
import json
import re
import shutil
import subprocess
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
SR = 48000
FFMPEG = shutil.which("ffmpeg") or "ffmpeg"


def load(path):
    raw = subprocess.run([FFMPEG, "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


lines = json.loads((ROOT / "data" / "lyrics.json").read_text(encoding="utf-8"))["lines"]


def line(q):
    return next(l for l in lines if q.lower() in l["text"].lower())


def word(q, w, nth=0):
    ws = [x for x in line(q)["words"] if norm(x["w"]) == norm(w)]
    return ws[nth]


def cut(q):
    l = line(q)
    i = lines.index(l)
    gap = l["start"] - lines[i - 1]["end"] if i else 1
    return l["start"] - min(0.18, max(0.04, gap * 0.45))


voice = load(ROOT / "audio" / "voiceover.mp3")
N = len(voice)
fx = np.zeros(N, np.float32)
cache = {}


def sfx(name, take=1):
    key = f"{name}_{take}"
    if key not in cache:
        p = ROOT / "audio" / "sfx" / f"{key}.mp3"
        cache[key] = load(p if p.exists() else ROOT / "audio" / "sfx" / f"{name}_1.mp3")
    return cache[key]


def put(name, t, db=0.0, take=1, align="start", dur=None):
    s = sfx(name, take)
    if dur:
        s = s[: int(dur * SR)].copy()
        s[-int(0.03 * SR):] *= np.linspace(1, 0, int(0.03 * SR))
    if align == "peak":
        t -= np.argmax(np.abs(s)) / SR
    elif align == "end":
        t -= len(s) / SR
    i = int(max(0.0, t) * SR)
    if i >= N:
        return
    e = min(N, i + len(s))
    fx[i:e] += s[: e - i] * (10 ** (db / 20))


W = word
# cuts
for n, q in enumerate(["This is our holo bot", "rolls a design DNA", "Every diagram is", "Packets stream", "So the pipeline", "Does it replace"]):
    put("whoosh_fast", cut(q), -8, take=1 + n % 2, align="peak")
# hook
put("riser", 0.0, -16, dur=1.6)
te = W("What if", "every")["start"]
put("spark_ignite", te - 0.05, -10)
put("pen_line", te, -12, dur=0.45)
for i in range(6):
    put("ui_tick", W("What if", "eight")["start"] + i * 0.05, -20)
th = W("What if", "hours…")["start"]
for i in range(3):
    put("pen_tick", th + i * 0.16, -9)
put("pen_line", W("nobody", "nobody")["start"], -12, dur=0.38)
tt = W("nobody", "touched")["start"] + 0.05
put("zap_slash", tt, -8)
put("zap_slash", tt + 0.14, -10)
# bot
for k in ["holo", "bot."]:
    w = W("This is our holo bot", k)
    put("pen_line", w["start"], -11, dur=max(0.3, w["end"] - w["start"]))
put("marker_strike", W("This is our holo bot", "bot.")["end"], -12)
for k in ["topic,", "script,", "fact-checks"]:
    w = W("It picks", k)
    put("pen_line", w["start"] - 0.05, -14, dur=0.35)
    put("typewriter", w["start"], -15, take=2 if k == "script," else 1, dur=0.45)
put("confirm_chime", W("It picks", "exists.")["start"], -9)
# dna
put("paper_slide", cut("rolls a design DNA"), -10)
put("pen_line", W("rolls a design", "design")["start"] - 0.1, -12, dur=0.9)
for k in ["palette,", "font", "camera", "hologram"]:
    w = W("rolls a design", k)
    put("ui_blip", w["start"], -12, take=1 + len(k) % 2)
    put("pen_tick", w["start"] + 0.2, -14)
put("stamp", W("No two videos", "same.")["start"] + 0.05, -4, align="peak")
# holo
put("projector_run", cut("Every diagram is"), -24, dur=9.0)
for k in ["Servers,", "databases,", "globes,"]:
    put("scan_sweep", W("Servers, databases", k)["start"] - 0.05, -9)
put("ui_tick", W("Servers, databases", "scanning")["start"], -12)
# flows
tp = W("Packets stream", "Packets")["start"]
put("spark_zip", tp, -9)
for i in range(10):
    put("spark_zip", tp + 0.9 + i * 0.55, -22, take=1)
put("ui_blip", W("Packets stream", "dotted")["start"], -12, take=2)
tc = W("Packets stream", "counters")["start"]
for i in range(14):
    put("ui_tick", tc + i * 0.09, -19)
put("whoosh_soft", W("Packets stream", "camera")["start"], -10)
# pipe
put("paper_slide", cut("So the pipeline"), -10)
for k in ["topic,", "script,", "voice,", "render,", "post."]:
    w = W("So the pipeline", k)
    put("pen_tick", w["start"] - 0.12, -15)
    put("typewriter", w["start"], -14, take=1 + len(k) % 2, dur=0.35)
for k in ["Nine", "three", "nine"]:
    w = W("Nine a.m.", k)
    put("pen_line", w["start"] - 0.05, -14, dur=0.35)
    put("mouse_click", w["start"] + 0.3, -10)
for k in ["YouTube", "Instagram."]:
    put("key_click", W("Nine a.m.", k)["start"] + 0.08, -10, take=1 + len(k) % 2)
put("stamp", W("Nine a.m.", "Instagram.")["end"] + 0.08, -3, align="peak")
# verdict
for k in ["three", "4K", "six"]:
    put("impact_slam" if k != "4K" else "impact_small", W("But three", k)["start"], -7 if k != "4K" else -6)
put("typewriter", W("But three", "autopilot?")["start"], -14, dur=0.6)
tw = W("pretty wild", "wild.")["start"]
put("riser", tw, -12, align="end")
put("impact_slam", tw, -5)
put("spark_sizzle", tw + 0.05, -12)
put("reverse_suck", N / SR - 0.4, -16, align="end")

# duck the effects under the voice (up to ~7 dB), sum, normalise loudness and soft-limit
win = int(0.08 * SR)
env = np.convolve(np.abs(voice), np.ones(win, np.float32) / win, mode="same")
duck = 10 ** (-7 * np.clip(env / (np.percentile(env, 90) + 1e-9), 0, 1) / 20)
mix = voice + fx * duck * 0.9
active = mix[np.abs(voice) > 0.02]
rms = np.sqrt(np.mean(active ** 2)) if len(active) else 0.1
mix *= 0.17 / (rms + 1e-9)                      # about -14 LUFS for speech
mix = np.tanh(mix * 1.05) / np.tanh(1.05)
mix *= 0.97 / max(1e-6, float(np.abs(mix).max()))
st = np.stack([mix, mix], axis=1)
out = ROOT / "out" / "mix.wav"
with wave.open(str(out), "wb") as wf:
    wf.setnchannels(2)
    wf.setsampwidth(2)
    wf.setframerate(SR)
    wf.writeframes((st * 32767).astype(np.int16).tobytes())
print(f"mix: {out} ({N / SR:.2f}s, {len(cache)} effects used)")
