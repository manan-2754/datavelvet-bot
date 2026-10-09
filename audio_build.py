"""
Audio for the Motion-as-Code bot.
  narrate(script): every scene line synthesised with edge-tts (word boundaries kept), written as
                   audio/voiceover.mp3 + data/lyrics.json (lines tagged with their scene, plus the scenes).
  mix(script):     the kit's sound effects placed on the same cue words the plates animate on, ducked under the
                   voice, loudness-normalised -> out/mix.wav.
"""
import asyncio
import json
import random
import re
import shutil
import subprocess
import wave
from pathlib import Path

import edge_tts
import numpy as np

ROOT = Path(__file__).resolve().parent
SR = 48000
VOICES = ["en-US-AndrewMultilingualNeural", "en-US-BrianMultilingualNeural"]
LEAD, IN_SCENE, BETWEEN, TAIL = 0.35, 0.28, 0.7, 1.8


def ffmpeg():
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    import os
    for p in Path(os.getenv("LOCALAPPDATA", "")).glob("Microsoft/WinGet/Packages/Gyan.FFmpeg*/*/bin/ffmpeg.exe"):
        return str(p)
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def norm(s):
    return re.sub(r"[^a-z0-9()]", "", s.lower())


def decode(path):
    raw = subprocess.run([ffmpeg(), "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


async def _synth(text, path, voice):
    words = []
    comm = edge_tts.Communicate(text, voice, rate="+2%", boundary="WordBoundary")
    with open(path, "wb") as f:
        async for ch in comm.stream():
            if ch["type"] == "audio":
                f.write(ch["data"])
            elif ch["type"] == "WordBoundary":
                s = ch["offset"] / 1e7
                words.append((ch["text"], s, s + ch["duration"] / 1e7))
    return words


def synth(text, path, voice):
    for attempt in range(4):
        try:
            words = asyncio.run(_synth(text, path, voice))
            if Path(path).stat().st_size > 1000:
                return words
        except Exception as e:
            print(f"  tts retry {attempt + 1}: {e}")
    raise RuntimeError(f"text-to-speech failed for: {text[:60]}")


def attach(tokens, bounds):
    out, j = [], 0
    for tok in tokens:
        target = norm(tok)
        if not target:
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
        if s0 is None:
            s0 = e0 = out[-1]["end"] if out else 0
        out.append({"w": tok, "start": round(s0, 3), "end": round(e0, 3)})
    return out


def narrate(script, voice=None):
    voice = voice or random.choice(VOICES)
    tmp = ROOT / "out" / "vo_tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True, exist_ok=True)
    track, t, lines, k = [np.zeros(int(LEAD * SR), np.float32)], LEAD, [], 0
    n = len(script["scenes"])
    for si, sc in enumerate(script["scenes"]):
        for li, text in enumerate(sc["lines"]):
            mp3 = tmp / f"l{k:03d}.mp3"
            k += 1
            bounds = synth(text, mp3, voice)
            audio = decode(mp3)
            nz = np.nonzero(np.abs(audio) > 0.004)[0]
            a0 = max(0, nz[0] - int(0.02 * SR)) if len(nz) else 0
            a1 = min(len(audio), nz[-1] + int(0.06 * SR)) if len(nz) else len(audio)
            clip = audio[a0:a1]
            dur = len(clip) / SR
            off = t - a0 / SR
            words = attach(text.split(), [(w, s + off, e + off) for w, s, e in bounds])
            for w in words:
                w["start"] = round(max(t, min(w["start"], t + dur)), 3)
                w["end"] = round(max(w["start"], min(w["end"], t + dur)), 3)
            lines.append({"text": text, "start": words[0]["start"], "end": round(t + dur, 3), "scene": si, "words": words})
            last = li == len(sc["lines"]) - 1
            pause = (TAIL if si == n - 1 else BETWEEN) if last else IN_SCENE
            track += [clip, np.zeros(int(pause * SR), np.float32)]
            t += dur + pause
    y = np.concatenate(track)
    y *= 0.89 / max(1e-6, float(np.abs(y).max()))
    wav = tmp / "voiceover.wav"
    with wave.open(str(wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes((np.clip(y, -1, 1) * 32767).astype(np.int16).tobytes())
    (ROOT / "audio").mkdir(exist_ok=True)
    (ROOT / "data").mkdir(exist_ok=True)
    subprocess.run([ffmpeg(), "-v", "error", "-y", "-i", str(wav), "-c:a", "libmp3lame", "-b:a", "256k",
                    str(ROOT / "audio" / "voiceover.mp3")], check=True)
    scenes = [{"plate": s["plate"], "title": s.get("title", ""), "data": s.get("data", {}),
               "meta": {"i": i, "n": n, "topic": script.get("topic", ""), "seed": script.get("seed", 0)}} for i, s in enumerate(script["scenes"])]
    (ROOT / "data" / "lyrics.json").write_text(json.dumps({"source": "audio_build.narrate (edge-tts)", "lines": lines,
                                                           "scenes": scenes}, indent=1, ensure_ascii=False), encoding="utf-8")
    return len(y) / SR, voice


# ------------------------------------------------------------------ sound design
def _q(a, b):
    """`a ?? b` exactly as the TS plates resolve a cue (an empty cue stays empty)."""
    return a if a is not None else b


class Cues:
    """Mirrors the plates' cue lookup (scenes/_gen.ts GenPlate.cue)."""

    def __init__(self, lines, scene):
        self.ws = [w for l in lines if l.get("scene") == scene for w in l["words"] if norm(w["w"])]
        self.cursor = 0

    def __call__(self, q, k=0, n=3):
        ws = self.ws
        if not ws:
            return None
        toks = [norm(x) for x in str(q or "").split() if norm(x)]

        def find(frm):
            if not toks:
                return -1
            for i in range(frm, len(ws) - len(toks) + 1):
                if all(norm(ws[i + j]["w"]) == tk for j, tk in enumerate(toks)):
                    return i
            for i in range(frm, len(ws)):
                if norm(ws[i]["w"]) == toks[0]:
                    return i
            return -1
        i = find(self.cursor)
        if i < 0:
            i = find(0)
        if i < 0:
            i = min(len(ws) - 1, round((k + 1) * len(ws) / (n + 1)))
        self.cursor = i + 1
        return ws[i]


def mix(script):
    ly = json.loads((ROOT / "data" / "lyrics.json").read_text(encoding="utf-8"))
    lines = ly["lines"]
    voice = decode(ROOT / "audio" / "voiceover.mp3")
    N = len(voice)
    fx = np.zeros(N, np.float32)
    cache = {}

    def sfx(name, take=1):
        key = f"{name}_{take}"
        if key not in cache:
            p = ROOT / "audio" / "sfx" / f"{key}.mp3"
            cache[key] = decode(p if p.exists() else ROOT / "audio" / "sfx" / f"{name}_1.mp3")
        return cache[key]

    def put(name, t, db=0.0, take=1, align="start", dur=None):
        if t is None:
            return
        s = sfx(name, take)
        if dur:
            s = s[: int(dur * SR)].copy()
            f = min(len(s), int(0.03 * SR))
            s[-f:] *= np.linspace(1, 0, f)
        if align == "peak":
            t -= np.argmax(np.abs(s)) / SR
        elif align == "end":
            t -= len(s) / SR
        i = int(max(0.0, t) * SR)
        if i >= N:
            return
        e = min(N, i + len(s))
        fx[i:e] += s[: e - i] * (10 ** (db / 20))

    scenes = script["scenes"]
    starts = []
    for si in range(len(scenes)):
        first = next((l for l in lines if l["scene"] == si), None)
        if not first:
            starts.append(None)
            continue
        idx = lines.index(first)
        gap = first["start"] - lines[idx - 1]["end"] if idx else 1
        starts.append(0.0 if si == 0 else first["start"] - min(0.2, max(0.04, gap * 0.45)))
    put("riser", 0.0, -16, dur=1.6)
    for si, sc in enumerate(scenes):
        t0 = starts[si]
        if t0 is None:
            continue
        nxt = next((s for s in starts[si + 1:] if s is not None), N / SR)
        if si:
            put("whoosh_fast", t0, -8, take=1 + si % 2, align="peak")
        cue, d, plate = Cues(lines, si), sc.get("data", {}), sc["plate"]
        T = lambda w, dt=0.0: (w["start"] + dt) if w else None
        its = (d.get("rows") if plate == "compare" else d.get("items")) or []
        if plate == "hook":
            w = cue(d.get("cue"), 0, 1)
            put("spark_ignite", T(w, -0.1), -10)
            m = d.get("motif")
            if m == "dial":
                put("pen_line", T(w, -0.2), -12, dur=0.5)
                for i in range(3):
                    put("pen_tick", T(w, 0.6 + i * 0.16), -9)
            elif m == "chart":
                put("pen_line", T(w, -0.25), -12, dur=1.0)
                put("ui_blip", T(w, 0.8), -10)
            elif m == "strike":
                put("pen_line", T(w, -0.45), -12, dur=0.4)
                put("zap_slash", T(w, 0.05), -8)
                put("zap_slash", T(w, 0.2), -10)
            elif m == "holo":
                put("projector_run", t0, -24, dur=max(1.0, nxt - t0))
                put("scan_sweep", T(w, -0.3), -8)
                put("impact_small", T(w, 0.6), -10)
            else:
                put("impact_slam", T(w), -7)
                put("pen_line", T(w, -0.1), -14, dur=0.7)
        elif plate == "title":
            w = cue(d.get("termCue") or d.get("term", "").split(" ")[0], 0, 4)
            put("pen_line", T(w), -11, dur=1.0)
            put("marker_strike", T(w, 1.0), -13)
            last = None
            for k, it in enumerate(its):
                w2 = cue(it.get("cue") or it.get("label"), k + 1, len(its) + 1)
                put("pen_line", T(w2, -0.08), -14, dur=0.4)
                put("typewriter", T(w2), -15, take=1 + k % 2, dur=0.4)
                last = w2
            if last:
                put("confirm_chime", last["end"] + 0.45, -10)
        elif plate == "specimen":
            put("paper_slide", t0, -10)
            put("pen_line", t0 + 0.2, -13, dur=1.3)
            lastw = None
            for k, it in enumerate(its):
                w2 = cue(it.get("cue") or it.get("label"), k, len(its))
                put("ui_blip", T(w2), -12, take=1 + k % 2)
                put("pen_tick", T(w2, 0.2), -14)
                lastw = w2
            if d.get("stamp"):
                ws = cue(d.get("stampCue"), 3, 4)
                ts = max(T(ws, 0.05) or 0, (lastw["start"] + 0.6) if lastw else 0)
                put("stamp", ts, -4, align="peak")
        elif plate in ("holo", "scene3d"):
            put("projector_run", t0, -24, dur=max(1.0, nxt - t0))
            ws3 = []
            for k, it in enumerate(its):
                w2 = cue(_q(it.get("cue"), it.get("label")), k, len(its))
                put("scan_sweep", T(w2, -0.05), -9)
                ws3.append(w2)
            if plate == "scene3d" and len(its) > 1 and ws3[-1]:
                tl = max(w["start"] for w in ws3 if w) + 0.35
                put("pen_line", tl, -15, dur=0.5)
                tp = T(cue(d.get("packetsCue"), len(its), len(its) + 1)) if d.get("packetsCue") else None
                tp = max(tp or 0, t0 + 0.5) if tp else tl + 0.5
                tt = tp
                while tt < nxt - 0.3:
                    put("spark_zip", tt, -10 if tt == tp else -22)
                    tt += 0.6
        elif plate == "layers":
            put("projector_run", t0, -26, dur=max(1.0, nxt - t0))
            last = None
            for k, it in enumerate(its):
                w2 = cue(_q(it.get("cue"), it.get("label")), k, len(its))
                put("whoosh_soft", T(w2, -0.1), -12)
                put("impact_small", T(w2, 0.45), -11)
                put("ui_blip", T(w2, 0.35), -15, take=1 + k % 2)
                last = w2
            if last and len(its) > 1:
                put("spark_zip", last["start"] + 0.8, -11)
        elif plate == "orbit":
            put("projector_run", t0, -24, dur=max(1.0, nxt - t0))
            core = d.get("core") if isinstance(d.get("core"), dict) else {}
            w0 = cue(_q(core.get("cue"), core.get("label")), 0, len(its) + 1)
            put("scan_sweep", T(w0, -0.05), -8)
            for k, it in enumerate(its):
                w2 = cue(_q(it.get("cue"), it.get("label")), k + 1, len(its) + 1)
                put("whoosh_soft", T(w2, -0.25), -14)
                put("ui_blip", T(w2), -12, take=1 + k % 2)
                put("spark_zip", T(w2, 0.6), -16)
        elif plate == "tunnel":
            put("projector_run", t0, -26, dur=max(1.0, nxt - t0))
            for k, it in enumerate(its):
                w2 = cue(_q(it.get("cue"), it.get("label")), k, len(its))
                put("whoosh_fast", T(w2, 0.05), -9, take=1 + k % 2, align="peak")
                put("impact_small", T(w2, 0.05), -12)
        elif plate == "bars3d":
            lastw = None
            for k, it in enumerate(its):
                w2 = cue(_q(it.get("cue"), it.get("value")), k, len(its))
                put("pen_line", T(w2), -15, dur=0.5)
                put("impact_slam" if k % 2 == 0 else "impact_small", T(w2, 0.55), -9)
                for i in range(6):
                    put("ui_tick", T(w2, i * 0.12), -21)
                lastw = w2
            if d.get("total") and lastw:
                put("typewriter", max(T(cue(d.get("totalCue"), len(its), len(its) + 1)) or 0, lastw["end"] + 0.3), -14, dur=0.6)
        elif plate == "flows":
            cue((d.get("hub") or {}).get("cue"), 0, 5)
            first_node = None
            for k, it in enumerate(its):
                w2 = cue(it.get("cue") or it.get("label"), k + 1, len(its) + 1)
                put("pen_tick", T(w2, -0.1), -15)
                first_node = first_node or w2
            tp = T(cue(d.get("packetsCue"), 1, 3)) if d.get("packetsCue") else ((first_node["start"] + 0.4) if first_node else t0 + 1)
            put("spark_zip", tp, -9)
            if tp:
                tt = tp + 0.9
                while tt < nxt - 0.3:
                    put("spark_zip", tt, -22)
                    tt += 0.55
            sw = [w for l in lines if l["scene"] == si for w in l["words"]]
            tc = T(cue(d.get("countersCue"), 2, 3)) if d.get("countersCue") else (sw[int(len(sw) * 0.45)]["start"] if sw else None)
            for i in range(12):
                put("ui_tick", (tc or t0) + i * 0.09, -19)
            if sw:
                put("whoosh_soft", sw[int(len(sw) * 0.7)]["start"], -11)
        elif plate == "form":
            put("paper_slide", t0, -10)
            lastw = None
            for k, it in enumerate(its):
                w2 = cue(it.get("cue") or it.get("label"), k, len(its))
                put("pen_tick", T(w2, -0.15), -15)
                put("typewriter", T(w2), -14, take=1 + k % 2, dur=0.35)
                lastw = w2
            if d.get("stamp") and lastw:
                ts = lastw["end"] + 0.35
                if d.get("stampCue"):
                    ts = max(T(cue(d.get("stampCue"), 4, 5)) or 0, lastw["end"] + 0.3)
                put("stamp", ts, -3, align="peak")
        elif plate == "stats":
            lastw = None
            for k, it in enumerate(its):
                w2 = cue(it.get("cue") or it.get("value"), k, len(its))
                put("impact_slam" if k % 2 == 0 else "impact_small", T(w2), -7 if k % 2 == 0 else -6)
                lastw = w2
            if d.get("total") and lastw:
                put("typewriter", max(T(cue(d.get("totalCue"), len(its), len(its) + 1)) or 0, lastw["end"] + 0.3), -14, dur=0.6)
        elif plate == "compare":
            put("pen_line", t0 + 0.15, -13, dur=0.7)
            put("ui_blip", t0 + 0.75, -11)
            for k, it in enumerate(its):
                w2 = cue(it.get("cue") or it.get("label"), k, len(its))
                put("typewriter", T(w2), -14, take=1 + k % 2, dur=0.6)
                put("impact_small", T(w2, 0.25), -12)
        elif plate == "outro":
            sw = [w for l in lines if l["scene"] == si for w in l["words"] if norm(w["w"])]
            if sw:
                te = sw[-1]["end"]
                put("riser", te, -13, align="end")
                put("impact_slam", te, -6)
                put("spark_sizzle", te + 0.05, -13)
            put("reverse_suck", N / SR - 0.4, -17, align="end")
    win = int(0.08 * SR)
    env = np.convolve(np.abs(voice), np.ones(win, np.float32) / win, mode="same")
    duck = 10 ** (-7 * np.clip(env / (np.percentile(env, 90) + 1e-9), 0, 1) / 20)
    out = voice + fx * duck * 0.9
    active = out[np.abs(voice) > 0.02]
    rms = np.sqrt(np.mean(active ** 2)) if len(active) else 0.1
    out *= 0.17 / (rms + 1e-9)
    out = np.tanh(out * 1.05) / np.tanh(1.05)
    out *= 0.97 / max(1e-6, float(np.abs(out).max()))
    st = np.stack([out, out], axis=1)
    path = ROOT / "out" / "mix.wav"
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes((st * 32767).astype(np.int16).tobytes())
    return path
