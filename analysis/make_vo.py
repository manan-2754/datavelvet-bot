"""Voiceover for the holo-bot promo: synthesises each script line with edge-tts (the holo bot's own voice),
keeps the word boundaries edge-tts reports, and writes audio/voiceover.mp3 + data/lyrics.json in the
engine's format (no forced alignment needed - the timings come straight from the synthesiser).

    python analysis/make_vo.py
"""
import asyncio
import json
import re
import subprocess
import shutil
import wave
from pathlib import Path

import edge_tts
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
VOICE = "en-US-AndrewMultilingualNeural"
RATE = "+2%"
SR = 48000
FFMPEG = shutil.which("ffmpeg") or "ffmpeg"

# (line text, pause after it in seconds). Longer pauses sit where the plates cut.
SCRIPT = [
    ("What if a bot made a 3D explainer video every eight hours…", 0.25),
    ("and nobody touched a thing?", 0.8),
    ("This is our holo bot.", 0.35),
    ("It picks a topic, writes the script, and fact-checks itself before a single frame exists.", 0.8),
    ("Then it rolls a design DNA: a palette, a font pair, a camera move, a hologram style.", 0.35),
    ("No two videos ever look the same.", 0.8),
    ("Every diagram is a real 3D hologram.", 0.35),
    ("Servers, databases, globes, printed out of a scanning ring, word by word.", 0.8),
    ("Packets stream along dotted connectors, counters update live, and the camera never stops moving.", 0.8),
    ("So the pipeline is simple: topic, script, voice, render, post.", 0.4),
    ("Nine a.m., three p.m., nine p.m. YouTube and Instagram.", 0.8),
    ("Does it replace a motion designer? Not really.", 0.45),
    ("But three 4K videos a day, for six months, on autopilot?", 0.35),
    ("That's pretty wild.", 1.6),
]
LEAD = 0.35


def norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


async def synth(text, path):
    words = []
    comm = edge_tts.Communicate(text, VOICE, rate=RATE, boundary="WordBoundary")
    with open(path, "wb") as f:
        async for ch in comm.stream():
            if ch["type"] == "audio":
                f.write(ch["data"])
            elif ch["type"] == "WordBoundary":
                s = ch["offset"] / 1e7
                words.append((ch["text"], s, s + ch["duration"] / 1e7))
    return words


def decode(path):
    raw = subprocess.run([FFMPEG, "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def attach(tokens, bounds):
    """Give every display token (punctuation attached) a start/end from the synthesiser's word boundaries."""
    out, j = [], 0
    for tok in tokens:
        target = norm(tok)
        if not target:                      # pure punctuation: zero-length at the previous end
            t = out[-1]["end"] if out else (bounds[0][1] if bounds else 0)
            out.append({"w": tok, "start": t, "end": t})
            continue
        acc, s0, e0 = "", None, None
        while j < len(bounds) and len(acc) < len(target):
            w, s, e = bounds[j]
            j += 1
            if not norm(w):
                continue
            acc += norm(w)
            s0 = s if s0 is None else s0
            e0 = e
        if s0 is None:                       # ran out: hang off the last word
            s0 = e0 = out[-1]["end"] if out else 0
        out.append({"w": tok, "start": round(s0, 3), "end": round(e0, 3)})
    return out


def main():
    tmp = ROOT / "out" / "vo_tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    track = [np.zeros(int(LEAD * SR), np.float32)]
    t = LEAD
    lines = []
    for i, (text, pause) in enumerate(SCRIPT):
        mp3 = tmp / f"line_{i:02d}.mp3"
        bounds = asyncio.run(synth(text, mp3))
        audio = decode(mp3)
        nz = np.nonzero(np.abs(audio) > 0.004)[0]           # trim edge-tts's leading/trailing silence
        a0 = max(0, nz[0] - int(0.02 * SR)) if len(nz) else 0
        a1 = min(len(audio), nz[-1] + int(0.06 * SR)) if len(nz) else len(audio)
        clip = audio[a0:a1]
        off = t - a0 / SR
        words = attach(text.split(), [(w, s + off, e + off) for w, s, e in bounds])
        for w in words:
            w["start"] = round(max(t, min(w["start"], t + len(clip) / SR)), 3)
            w["end"] = round(max(w["start"], min(w["end"], t + len(clip) / SR)), 3)
        lines.append({"text": text, "start": words[0]["start"], "end": round(t + len(clip) / SR, 3), "words": words})
        print(f"  {i:2d}  {t:6.2f}s  {text}")
        track += [clip, np.zeros(int(pause * SR), np.float32)]
        t += len(clip) / SR + pause
    y = np.concatenate(track)
    y *= 0.89 / max(1e-6, float(np.abs(y).max()))
    wav = tmp / "voiceover.wav"
    with wave.open(str(wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes((np.clip(y, -1, 1) * 32767).astype(np.int16).tobytes())
    subprocess.run([FFMPEG, "-v", "error", "-y", "-i", str(wav), "-c:a", "libmp3lame", "-b:a", "256k",
                    str(ROOT / "audio" / "voiceover.mp3")], check=True)
    (ROOT / "data" / "lyrics.json").write_text(json.dumps({"source": "make_vo.py (edge-tts word boundaries)", "lines": lines},
                                                          indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"voiceover: {len(y) / SR:.2f}s, {len(lines)} lines")


if __name__ == "__main__":
    main()
