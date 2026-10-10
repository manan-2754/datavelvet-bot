"""
Motion-as-Code bot - explainer videos in the hand-plotted engineering style, fully automatic:
  topic -> LLM script (plates + cue words, fact-checked) -> edge-tts voice with word timings -> the TypeScript /
  three.js engine renders every frame in headless Chrome -> sound design mix -> YouTube Shorts + Instagram Reels.

  python main.py                         # make one video from the next topic (nothing posted)
  python main.py --show                  # ... and open it in VLC
  python main.py --script out/x.json     # render an existing script
  python main.py --post                  # make one video and upload it (what the cloud job runs)
"""
import argparse
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
try:
    from dotenv import load_dotenv
    load_dotenv(BASE / ".env", override=True)
except ImportError:
    pass

import art_director  # noqa: E402
import audio_build  # noqa: E402
import analytics  # noqa: E402
import composer  # noqa: E402
import critic  # noqa: E402
import research  # noqa: E402
import trends  # noqa: E402
import writer  # noqa: E402

OUT = BASE / "out"
STATE = BASE / "state.json"
BUNDLE = BASE / "out" / "bundle.json"
RUN_UNTIL = os.getenv("RUN_UNTIL") or "2027-04-09"
FPS = os.getenv("RENDER_FPS") or "30"
SAMPLES = os.getenv("RENDER_SAMPLES") or "2"
VLC = r"C:\Program Files\VideoLAN\VLC\vlc.exe"


SERIES = [
    ("System Design", ["load balanc", "cach", "shard", "replica", "database", "queue", "rate limit", "cap theorem", "consensus", "paxos",
                       "raft", "microservice", "kafka", "redis", "index", "scal"]),
    ("How the Internet Works", ["dns", "tcp", "http", "tls", "websocket", "router", "packet", "cdn", "email", "wifi", "5g", "ip address"]),
    ("Under the Hood", ["garbage", "compiler", "docker", "container", "kernel", "memory", "thread", "cpu", "gpu", "virtual machine",
                        "jvm", "interpreter", "operating system", "git"]),
    ("AI Explained", ["neural", "llm", "transformer", "gpt", "machine learning", "embedding", "diffusion", " ai", "model"]),
    ("Security Decoded", ["encrypt", "hash", "password", "jwt", "oauth", "xss", "injection", "firewall", "vpn", "zero trust", "2fa"]),
]
LEVELS = ["beginner", "engineer", "engineer", "deep dive"]


def series_of(topic):
    low = f" {topic.lower()} "
    return next((name for name, keys in SERIES if any(k in low for k in keys)), "Tech Explained")


def series_info(topic, state, fresh):
    name = series_of(topic)
    ep = 1 + sum(1 for p in state.get("posts", []) if (p.get("features") or {}).get("series") == name)
    nxt = next((t for t in fresh if t != topic and series_of(t) == name), None)
    return {"name": name, "ep": ep, "next": nxt}


def pick_level(state):
    lv = LEVELS[len(state.get("posts", [])) % len(LEVELS)]
    best = ((state.get("insights") or {}).get("best") or {}).get("level") or []
    return best[0] if best and random.random() < 0.5 else lv


def add_sources(script, sources):
    if not sources:
        return
    yt = script.setdefault("youtube", {})
    yt["description"] = (yt.get("description", "") + "\n\nSources:\n" + "\n".join(sources[:4]) +
                         "\n\nScript fact-checked against these sources by AI. Visuals and voice are AI-generated.")[:4900]
    script["instagram_caption"] = (script.get("instagram_caption", "") + "\n\nFact-checked. Sources: " +
                                   ", ".join(s.split("/")[2] for s in sources[:3] if "//" in s))[:2150]
    script["sources"] = sources


def features(script, meta):
    st = script.get("style") or {}
    d = meta.get("duration") or 0
    return {"angle": script.get("angle"), "layouts": (script.get("format") or "").split(" > "),
            "types": sorted({e.get("type") for s in script["scenes"] for e in (s.get("data") or {}).get("elements", []) if e.get("type")}),
            "cams": [(s.get("data") or {}).get("camera") for s in script["scenes"] if (s.get("data") or {}).get("camera")],
            "hue": (st.get("name") or "").split(" ")[0], "voice": meta.get("voice"), "music": (script.get("music") or "").split(" ")[0],
            "length": "short" if d < 50 else ("mid" if d < 75 else "long"), "level": script.get("level"),
            "trend": bool(script.get("trend")), "series": (script.get("series") or {}).get("name")}


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:50] or "video"


def tool(name):
    exe = shutil.which(name)
    if exe:
        return exe
    if name in ("bun", "bunx"):
        for p in (Path.home() / ".bun" / "bin" / f"{name}.exe",
                  *Path(os.getenv("LOCALAPPDATA", "")).glob(f"Microsoft/WinGet/Packages/Oven-sh.Bun*/bun-windows-x64/{name}.exe")):
            if p.exists():
                return str(p)
    raise RuntimeError(f"{name} not found on PATH")


def env_with_tools():
    env = dict(os.environ)
    dirs = {str(Path(audio_build.ffmpeg()).parent), str(Path(tool("bun")).parent)}
    env["PATH"] = os.pathsep.join([*dirs, env.get("PATH", "")])
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env


def load_state():
    st = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    for k in ("used_topics", "posts", "used_formats"):
        st.setdefault(k, [])
    return st


def pick_seed(state):
    """Visual seed for a video: hologram tint, floors, reveal styles and camera moves all derive from it.
    It never repeats the previous video's tint or camera rotation."""
    last = next((p.get("seed") for p in reversed(state.get("posts", [])) if p.get("seed")), None)
    rng = random.SystemRandom()
    while True:
        s = rng.randrange(1, 2 ** 31)
        if last is None or (s % 6 != last % 6 and (s >> 7) % 4 != (last >> 7) % 4):
            return s


def prepare_video(script, voice=None, tag=""):
    """Everything before the frames: script file, narration with word timings, audio analysis, art-critic pass."""
    if any(sc["plate"] == "edit" for sc in script["scenes"]):
        writer.prepare_edits(script)
    out_dir = OUT / f"{time.strftime('%Y%m%d-%H%M%S')}_{slugify(script['topic'])}{tag}"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "script.json").write_text(json.dumps(script, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"🧩 Plates: {script.get('format') or ' > '.join(s['plate'] for s in script['scenes'])}  (visual seed {script.get('seed')})")
    st_ = script.get("style") or {}
    print(f"🎨 Style: {st_.get('name')}  |  angle: {script.get('angle')}  |  cameras: {' '.join(s['cam'] for s in st_.get('scenes', []))}")
    print("🔊 Narration")
    dur, voice = audio_build.narrate(script, voice)
    print(f"  {voice}, {dur:.1f}s")
    if dur > 170:
        raise RuntimeError(f"video would be {dur:.0f}s - too long for Shorts")
    env = env_with_tools()
    subprocess.run([sys.executable, str(BASE / "analysis" / "audio_vo.py")], cwd=BASE, env=env, check=True)
    print("🧐 " + critic.review(env, tool))
    return {"out_dir": str(out_dir), "dur": dur, "voice": voice}


def render_range(out, frm=None, to=None):
    """Render the whole video, or one frame-exact slice of it (split rendering across cloud machines)."""
    env = env_with_tools()
    cmd = [tool("bun"), "scripts/render.ts", "video", "--fps", FPS, "--samples", SAMPLES, "--shutter", "0.5", "--crf", "18", "--out", str(out)]
    if frm is not None:
        cmd += ["--from", f"{frm:.6f}", "--to", f"{to:.6f}", "--noaudio"]
    if SAMPLES == "auto":
        cmd += ["--min-samples", "2", "--max-samples", "8"]
    t0 = time.time()
    subprocess.run(cmd, cwd=BASE / "app", env=env, check=True)
    print(f"  rendered in {time.time() - t0:.0f}s")


def chunks(n):
    """n frame-exact slices covering the narration (boundaries on whole frames, so the stitched video is seamless)."""
    dur = json.loads((BASE / "data" / "audio.json").read_text(encoding="utf-8"))["duration"]
    fps = int(FPS)
    total = round(dur * fps)
    b = [round(k * total / n) for k in range(n + 1)]
    return [[b[k] / fps, (b[k + 1] / fps) if k < n - 1 else dur] for k in range(n) if b[k + 1] > b[k]]


def make_video(script, show=False, voice=None, tag=""):
    ctx = prepare_video(script, voice, tag)
    print(f"🎬 Rendering 1080x1920 @ {FPS} fps (samples {SAMPLES})")
    raw = OUT / "raw.mp4"
    render_range(raw)
    return finish_video(script, ctx, raw, show)


def finish_video(script, ctx, raw, show=False):
    out_dir, dur, voice = Path(ctx["out_dir"]), ctx["dur"], ctx["voice"]
    out_dir.mkdir(parents=True, exist_ok=True)
    print("🎵 Sound design")
    mixed = audio_build.mix(script)
    video = out_dir / "video.mp4"
    subprocess.run([audio_build.ffmpeg(), "-v", "error", "-y", "-i", str(raw), "-i", str(mixed), "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest", str(video)], check=True)
    raw.unlink(missing_ok=True)
    meta = {**script.get("youtube", {}), "instagram_caption": script.get("instagram_caption", ""), "topic": script["topic"],
            "duration": round(dur, 1), "voice": voice, "format": script.get("format"), "seed": script.get("seed"),
            "style_name": (script.get("style") or {}).get("name"), "angle": script.get("angle"),
            "review": script.get("review"), "music": script.get("music"), "sources": script.get("sources", []),
            "cover_ms": cover_ms()}
    meta["features"] = features(script, meta)
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"✅ {video} ({video.stat().st_size / 1e6:.1f} MB, {dur:.0f}s)")
    if show and Path(VLC).exists():
        subprocess.Popen([VLC, str(video)])
    return video, meta


def upload(video, meta, state):
    rec = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "topic": meta["topic"], "format": meta.get("format"),
           "seed": meta.get("seed"), "features": meta.get("features")}
    ok = True
    if os.getenv("AUTO_POST_YOUTUBE", "false").lower() == "true":
        try:
            from youtube_upload import upload_video
            rec["youtube_id"] = upload_video(video, meta)              # marked as AI / synthetic content
        except Exception as e:
            ok = False
            print(f"❌ YouTube upload failed: {e}")
    if os.getenv("AUTO_POST_INSTAGRAM", "false").lower() == "true":
        try:
            from instagram_upload import upload_reel
            rec["instagram_id"] = upload_reel(video, meta["instagram_caption"], meta.get("cover_ms"))   # AI-info label
        except Exception as e:
            ok = False
            print(f"❌ Instagram upload failed: {e}")
    state["posts"].append(rec)
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", help="render this script JSON instead of writing a new one")
    ap.add_argument("--topic", help="override the next topic")
    ap.add_argument("--show", action="store_true", help="open the result in VLC")
    ap.add_argument("--post", action="store_true", help="upload after rendering (what the cloud job runs)")
    ap.add_argument("--trend", action="store_true", help="pick a trending topic (the cloud does this for one slot a day)")
    ap.add_argument("--lang", default=os.getenv("EXTRA_LANGS", ""), help="also render translated versions, e.g. es,pt")
    ap.add_argument("--stage", choices=["prepare", "render", "finish"], help="cloud split render: prepare -> N x render -> finish")
    ap.add_argument("--chunk", type=int, default=0, help="slice index for --stage render")
    args = ap.parse_args()
    if args.stage == "render":
        return stage_render(args.chunk)
    if args.stage == "finish":
        return stage_finish(args.post)
    if args.post and date.today().isoformat() > RUN_UNTIL:
        print(f"Posting window ended on {RUN_UNTIL}.")
        gh_output(has_video="false", chunks="[]")
        return 0
    state = load_state()
    art_director.prune(state)          # styles posted more than 3 hours ago are forgotten
    try:                               # the learning loop: fresh stats -> what works -> next script
        n = analytics.collect(state)
        ins = analytics.learn(state)
        print(f"📈 Analytics: {n} post(s) refreshed, learning from {ins.get('n', 0)} rated video(s)")
        if args.post and analytics.reach_check(state) and analytics.should_skip(state):
            print(f"⏸️ Throttled ({state['throttle'].get('reason')}) - skipping this slot")
            gh_output(has_video="false", chunks="[]")
            STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
            return 0
    except Exception as e:
        print(f"  analytics skipped ({e})")
    topic, angle = None, None
    if args.script:
        script = json.loads(Path(args.script).read_text(encoding="utf-8"))
        script = writer.validate(script) if "format" not in script else script
    elif state.get("queued_scripts"):          # pre-approved scripts (already validated + fact-checked) go first
        script = state["queued_scripts"].pop(0)
        topic = script["topic"]
        print(f"📌 Topic (queued script): {topic}")
    else:
        topics = json.loads((BASE / "topics.json").read_text(encoding="utf-8"))
        failed = state.setdefault("failed_topics", {})
        fresh = [t for t in topics if t not in state["used_topics"] and failed.get(t, 0) < 2] or topics
        topic = args.topic or fresh[0]
        trend = None
        if not args.topic and (args.trend or (args.post and len(state["posts"]) % 3 == 1)):
            trend = trends.pick(set(state["used_topics"]) | set(topics), writer.llm)
            if trend:
                topic = trend["topic"]
                print(f"🔥 Trending topic: {topic}  ({trend['why']})")
        print(f"📌 Topic: {topic}")
        facts = research.gather(topic, llm=writer.llm)
        print(f"📚 Research: {len(facts['sources'])} source(s)  {' '.join(facts['sources'])}")
        series = series_info(topic, state, fresh)
        level = pick_level(state)
        print(f"🎞️ Series: {series['name']} · EP {series['ep']} · level {level}" + (f"  (next: {series['next']})" if series.get("next") else ""))
        try:
            angle = art_director.pick_angle(state)
            print(f"🎬 Angle: {angle[0]}  (every scene composed from scratch)")
            try:
                script = composer.write(topic, banned=state.get("scene_signatures", []), recent=state.get("compose_formats", []),
                                        angle=angle, seed=time.time_ns(), facts=facts, hints=analytics.hints(state), level=level,
                                        series=series)
                script.update(series=series, level=level, trend=trend)
                add_sources(script, facts["sources"] + ((trend or {}).get("sources") or []))
            except Exception as e:
                print(f"  composer failed ({e}) - falling back to the template writer")
                hook = art_director.pick_hook(state)
                script = writer.write_script(topic, art_director.recent_formats(state), seed=time.time_ns(), angle=angle, hook=hook)
        except Exception:
            if args.post:                    # a topic that fails twice is skipped, so it can never block the queue
                failed[topic] = failed.get(topic, 0) + 1
                STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
            raise
        script["topic"] = script.get("topic") or topic
    script["seed"] = script.get("seed") or pick_seed(state)
    script["angle"] = script.get("angle") or (angle[0] if angle else None)
    script["style"] = script.get("style") or art_director.new_genome(
        state, len(script["scenes"]), hook=(script["scenes"][0].get("data") or {}).get("motif"))
    if args.stage == "prepare":                # cloud split render, step 1: everything but the frames
        ctx = prepare_video(script)
        parts = chunks(int(os.getenv("RENDER_CHUNKS", "10")))
        BUNDLE.write_text(json.dumps({"script": script, "ctx": ctx, "topic": topic, "topic_override": bool(args.topic), "chunks": parts},
                                     ensure_ascii=False), encoding="utf-8")
        STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
        gh_output(has_video="true", chunks=json.dumps(list(range(len(parts)))))
        print(f"📦 Bundle ready: {len(parts)} slices of ~{ctx['dur'] / len(parts):.1f}s")
        return 0
    video, meta = make_video(script, args.show)
    for lang in [x.strip() for x in (args.lang or "").split(",") if x.strip()]:
        try:
            tr = composer.translate(script, lang)
            make_video(tr, args.show, voice=composer.LANG_VOICES.get(lang), tag=f"_{lang}")
        except Exception as e:
            print(f"  {lang} version skipped ({e})")
    if not args.post:
        print("(local run - nothing posted, state unchanged)")
        return 0
    return publish(script, video, meta, state, topic, bool(args.topic))


def gh_output(**kv):
    path = os.getenv("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            for k, v in kv.items():
                f.write(f"{k}={v}\n")


def stage_render(i):
    """Cloud split render, step 2: one machine renders slice i of the prepared video."""
    b = json.loads(BUNDLE.read_text(encoding="utf-8"))
    frm, to = b["chunks"][i]
    out = OUT / "chunks" / f"chunk_{i:02d}.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    print(f"🎬 Slice {i + 1}/{len(b['chunks'])}: {frm:.2f}s - {to:.2f}s @ {FPS} fps (samples {SAMPLES})")
    render_range(out, frm, to)
    return 0


def stage_finish(post):
    """Cloud split render, step 3: stitch the slices, mix the sound, post, save state."""
    b = json.loads(BUNDLE.read_text(encoding="utf-8"))
    parts = sorted((OUT / "chunks").glob("chunk_*.mp4"))
    if len(parts) != len(b["chunks"]):
        raise RuntimeError(f"only {len(parts)} of {len(b['chunks'])} slices rendered")
    lst = OUT / "chunks" / "list.txt"
    lst.write_text("".join(f"file '{p.resolve().as_posix()}'\n" for p in parts), encoding="utf-8")
    raw = OUT / "raw.mp4"
    subprocess.run([audio_build.ffmpeg(), "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(raw)], check=True)
    print(f"🧵 Stitched {len(parts)} slices")
    script = b["script"]
    video, meta = finish_video(script, b["ctx"], raw)
    if not post:
        print("(not posting)")
        return 0
    return publish(script, video, meta, load_state(), b.get("topic"), b.get("topic_override"))


def publish(script, video, meta, state, topic, topic_override):
    if topic and not topic_override:
        state["used_topics"].append(topic)
    state["used_formats"].append(script.get("format", ""))
    ok = upload(video, meta, state)
    state.setdefault("runs", []).append({"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "ok": ok,
                                         **({} if ok else {"error": "upload failed on a platform"})})
    state["runs"] = state["runs"][-200:]
    if script.get("series"):
        state["series"] = {"name": script["series"]["name"], "ep": script["series"]["ep"]}
    if state["posts"] and (state["posts"][-1].get("youtube_id") or state["posts"][-1].get("instagram_id")):
        art_director.remember(state, script["style"], script.get("format"), script.get("angle"))
        if script.get("signatures"):           # composed scenes are never reused, ever
            state.setdefault("scene_signatures", []).extend(script["signatures"])
            state.setdefault("compose_formats", []).append(script.get("format"))
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0 if ok else 2


def cover_ms():
    """Instagram cover frame: the moment the hook's headline has fully landed."""
    try:
        ly = json.loads((BASE / "data" / "lyrics.json").read_text(encoding="utf-8"))
        hook = [l for l in ly["lines"] if l.get("scene") == 0]
        return int(max(0.5, hook[-1]["end"] - 0.15) * 1000) if hook else 1500
    except Exception:
        return None


def run():
    """main() with a run log: failures are recorded in state.json for the weekly report."""
    try:
        return main()
    except Exception as e:
        if "--post" in sys.argv:
            try:
                st = load_state()
                st.setdefault("runs", []).append({"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "ok": False,
                                                  "error": f"{type(e).__name__}: {e}"[:300]})
                STATE.write_text(json.dumps(st, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception:
                pass
        raise


if __name__ == "__main__":
    sys.exit(run())
