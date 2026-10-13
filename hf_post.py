"""HyperFrames post pass: a WebGL shader transition + kinetic chapter card at every chapter change.

For each chapter boundary T the rendered video is cut into two short clips around T (A holds its last frame,
B holds its first), HyperFrames composites A -> B with one of its shader transitions and lays a chapter card on
top, and the 2 s result replaces that stretch of the video frame for frame, so narration sync never moves.
Needs Node >= 22 and `npm install` in hf/. Any failure leaves the original video untouched.
"""
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import audio_build

ROOT = Path(__file__).resolve().parent
HF = ROOT / "hf"
PRE, POST = 0.4, 1.6                    # seconds kept before / after the chapter change
T_DUR = 0.5                             # shader transition length, centred on the change
SHADERS = ["domain-warp", "light-leak", "cinematic-zoom", "chromatic-split", "glitch", "gravitational-lens",
           "ripple-waves", "sdf-iris", "cross-warp-morph", "whip-pan", "swirl-vortex", "ridged-burn"]

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<script src="gsap.min.js"></script>
<script src="hyper-shader.global.js"></script>
<style>
@font-face {{ font-family: "Archivo"; src: url("Archivo-900.ttf"); font-weight: 900; }}
@font-face {{ font-family: "Archivo"; src: url("Archivo-500.ttf"); font-weight: 500; }}
html, body {{ margin: 0; width: 1080px; height: 1920px; overflow: hidden; background: #05070c; }}
#root {{ position: relative; width: 100%; height: 100%; overflow: hidden; font-family: "Archivo", sans-serif; }}
.scene {{ position: absolute; inset: 0; overflow: hidden; opacity: 0; }}
#sA {{ opacity: 1; }}
.scene video {{ position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }}
#card {{ position: absolute; left: 0; right: 0; top: 1060px; height: 330px; }}
#band {{ position: absolute; left: 60px; right: 60px; top: 0; height: 330px; border-radius: 34px;
        background: linear-gradient(120deg, rgba(8,11,18,0.88), rgba(8,11,18,0.62));
        border: 2px solid {tint}66; box-shadow: 0 30px 80px rgba(0,0,0,0.55), 0 0 60px {tint}33; }}
#num {{ position: absolute; left: 110px; top: 40px; font-weight: 900; font-size: 230px; line-height: 250px;
       color: {tint}; text-shadow: 0 0 40px {tint}88; }}
#label {{ position: absolute; left: 420px; top: 92px; font-weight: 500; font-size: 34px; letter-spacing: 10px; color: #9aa4b2; }}
#name {{ position: absolute; left: 420px; top: 140px; right: 90px; font-weight: 900; font-size: {size}px; line-height: 1.0;
        color: #ffffff; white-space: nowrap; }}
#sweep {{ position: absolute; left: 60px; top: 0; width: 220px; height: 330px; border-radius: 34px;
         background: linear-gradient(90deg, transparent, rgba(255,255,255,0.22), transparent); }}
#bar {{ position: absolute; left: 420px; top: 262px; height: 8px; width: 520px; border-radius: 4px; background: {tint}; }}
</style>
</head>
<body>
<div id="root" data-composition-id="chapter" data-start="0" data-width="1080" data-height="1920" data-duration="{dur}" data-fps="{fps}">
  <div id="sA" class="scene"><video id="va" class="clip" src="a.mp4" muted playsinline data-start="0" data-duration="{dur}"></video></div>
  <div id="sB" class="scene">
    <video id="vb" class="clip" src="b.mp4" muted playsinline data-start="0" data-duration="{dur}"></video>
    <div id="card">
      <div id="band"></div><div id="sweep"></div>
      <div id="num">{num}</div><div id="label">CHAPTER</div><div id="name">{name}</div><div id="bar"></div>
    </div>
  </div>
</div>
<script>
const tl = gsap.timeline({{ paused: true }});
tl.fromTo("#band", {{ scaleX: 0.2, opacity: 0 }}, {{ scaleX: 1, opacity: 1, duration: 0.35, ease: "power3.out", transformOrigin: "left center" }}, 0.45);
tl.fromTo("#num", {{ y: 90, opacity: 0, scale: 1.4 }}, {{ y: 0, opacity: 1, scale: 1, duration: 0.4, ease: "back.out(2)" }}, 0.55);
tl.fromTo("#label", {{ x: -40, opacity: 0 }}, {{ x: 0, opacity: 1, duration: 0.3, ease: "power2.out" }}, 0.62);
tl.fromTo("#name", {{ x: 80, opacity: 0 }}, {{ x: 0, opacity: 1, duration: 0.4, ease: "expo.out" }}, 0.66);
tl.fromTo("#bar", {{ scaleX: 0 }}, {{ scaleX: 1, duration: 0.6, ease: "power2.inOut", transformOrigin: "left center" }}, 0.72);
tl.fromTo("#sweep", {{ x: -260, opacity: 0 }}, {{ x: 940, opacity: 1, duration: 0.7, ease: "power1.inOut" }}, 0.8);
tl.to("#card", {{ y: 60, opacity: 0, duration: 0.3, ease: "power2.in" }}, {out});
HyperShader.init({{ bgColor: "#05070c", accentColor: "{tint}", scenes: ["sA", "sB"],
  transitions: [{{ time: {t0}, shader: "{shader}", duration: {td}, ease: "power2.inOut" }}], timeline: tl, compositionId: "chapter" }});
window.__timelines["chapter"] = tl;
</script>
</body>
</html>
"""


def boundaries(lyrics):
    """(time, chapter index, chapter name) wherever the narration moves to a new stage."""
    out, prev = [], None
    for ln in lyrics["lines"]:
        d = lyrics["scenes"][ln["scene"]].get("data") or {}
        st, names = d.get("stage"), d.get("stages") or []
        if st is not None and prev is not None and st != prev and st < len(names):
            out.append((ln["start"], st, names[st]))
        if st is not None:
            prev = st
    return out


def _ff(*args):
    subprocess.run([audio_build.ffmpeg(), "-v", "error", "-y", *map(str, args)], check=True)


def _probe(video):
    ffprobe = str(Path(audio_build.ffmpeg()).with_name(Path(audio_build.ffmpeg()).name.replace("ffmpeg", "ffprobe")))
    out = subprocess.run([ffprobe, "-v", "error", "-select_streams", "v:0", "-count_packets",
                          "-show_entries", "stream=r_frame_rate,nb_read_packets", "-of", "json", str(video)],
                         capture_output=True, text=True, check=True)
    s = json.loads(out.stdout)["streams"][0]
    a, b = s["r_frame_rate"].split("/")
    return round(int(a) / int(b)), int(s["nb_read_packets"])


def _segment(raw, work, fps, f0, fc, f1, num, name, tint, shader):
    """Render frames [f0, f1) of raw with a shader transition at frame fc into work/seg.mp4."""
    work, raw = Path(work).resolve(), Path(raw).resolve()
    work.mkdir(parents=True, exist_ok=True)
    n = f1 - f0
    _ff("-i", raw, "-vf", f"trim=start_frame={f0}:end_frame={fc},setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop={n - (fc - f0)}",
        "-an", "-c:v", "libx264", "-crf", "12", "-preset", "veryfast", "-pix_fmt", "yuv420p", work / "a.mp4")
    _ff("-i", raw, "-vf", f"trim=start_frame={fc}:end_frame={f1},setpts=PTS-STARTPTS,tpad=start_mode=clone:start={fc - f0}",
        "-an", "-c:v", "libx264", "-crf", "12", "-preset", "veryfast", "-pix_fmt", "yuv420p", work / "b.mp4")
    for src, dst in [(HF / "node_modules/gsap/dist/gsap.min.js", "gsap.min.js"),
                     (HF / "node_modules/@hyperframes/shader-transitions/dist/index.global.js", "hyper-shader.global.js"),
                     (ROOT / "app/public/fonts/Archivo-w1000-900.ttf", "Archivo-900.ttf"),
                     (ROOT / "app/public/fonts/Archivo-w1000-500.ttf", "Archivo-500.ttf")]:
        shutil.copy(src, work / dst)
    dur = n / fps
    name = name.upper()
    (work / "index.html").write_text(PAGE.format(
        tint=tint, dur=f"{dur:.4f}", fps=fps, num=f"{num:02d}", name=name, size=96 if len(name) <= 9 else max(56, int(96 * 9 / len(name))),
        out=f"{dur - 0.32:.3f}", t0=f"{(fc - f0) / fps - T_DUR / 2:.3f}", td=T_DUR, shader=shader), encoding="utf-8")
    npx = shutil.which("npx") or "npx"
    env = {**os.environ, "HYPERFRAMES_NO_TELEMETRY": "1", "DO_NOT_TRACK": "1"}
    subprocess.run([npx, "--no-install", "hyperframes", "render", str(work), "-o", str(work / "seg.mp4"),
                    "--fps", str(fps), "--quality", "looks", "--quiet"], check=True, env=env, cwd=str(HF),
                   capture_output=True, text=True, timeout=900)
    _, got = _probe(work / "seg.mp4")
    if got != n:
        raise RuntimeError(f"segment has {got} frames, expected {n}")
    return work / "seg.mp4"


def apply(raw, script, lyrics_path=ROOT / "data" / "lyrics.json"):
    """Return a new silent video with HyperFrames chapter transitions, or the original on any failure."""
    raw = Path(raw)
    try:
        lyrics = json.loads(Path(lyrics_path).read_text(encoding="utf-8"))
        cuts = boundaries(lyrics)
        if not cuts or not (HF / "node_modules" / "hyperframes").exists():
            return raw
        fps, total = _probe(raw)
        tint = next((s.get("data", {}).get("tint") for s in script.get("scenes", []) if s.get("data", {}).get("tint")), "#22D3EE")
        seed = int(hashlib.sha1(script.get("topic", "").encode()).hexdigest(), 16)
        work = ROOT / "out" / "hf_tmp"
        shutil.rmtree(work, ignore_errors=True)
        pieces, at = [], 0
        for k, (t, st, name) in enumerate(cuts):
            fc = round(t * fps)
            f0, f1 = fc - round(PRE * fps), fc + round(POST * fps)
            if f0 <= at or f1 >= total:
                continue
            shader = SHADERS[(seed + k * 5) % len(SHADERS)]
            seg = _segment(raw, work / f"c{k}", fps, f0, fc, f1, st + 1, name, tint, shader)
            print(f"  ✨ chapter {st + 1} '{name}' at {t:.1f}s: {shader}")
            pieces += [("raw", at, f0), ("seg", seg)]
            at = f1
        if not pieces:
            return raw
        pieces.append(("raw", at, total))
        ins, chains, labels, n_in = ["-i", str(raw)], [], [], 1
        for i, p in enumerate(pieces):
            if p[0] == "raw":
                chains.append(f"[0:v]trim=start_frame={p[1]}:end_frame={p[2]},setpts=PTS-STARTPTS,format=yuv420p[p{i}]")
            else:
                ins += ["-i", str(p[1])]
                chains.append(f"[{n_in}:v]setpts=PTS-STARTPTS,format=yuv420p[p{i}]")
                n_in += 1
            labels.append(f"[p{i}]")
        out = raw.with_name(raw.stem + "_hf.mp4")
        _ff(*ins, "-filter_complex", ";".join(chains) + ";" + "".join(labels) + f"concat=n={len(pieces)}:v=1:a=0[v]",
            "-map", "[v]", "-r", fps, "-c:v", "libx264", "-crf", "17", "-preset", "medium", "-pix_fmt", "yuv420p", out)
        if _probe(out)[1] != total:
            raise RuntimeError("frame count changed")
        shutil.rmtree(work, ignore_errors=True)
        return out
    except Exception as e:
        msg = getattr(e, "stderr", "") or ""
        print(f"  HyperFrames chapter pass skipped ({str(e)[:160]} {str(msg)[-300:]})")
        return raw
