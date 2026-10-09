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

import audio_build  # noqa: E402
import writer  # noqa: E402

OUT = BASE / "out"
STATE = BASE / "state.json"
RUN_UNTIL = os.getenv("RUN_UNTIL") or "2027-04-09"
FPS = os.getenv("RENDER_FPS") or "30"
SAMPLES = os.getenv("RENDER_SAMPLES") or "2"
VLC = r"C:\Program Files\VideoLAN\VLC\vlc.exe"


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


def make_video(script, show=False):
    out_dir = OUT / f"{time.strftime('%Y%m%d-%H%M%S')}_{slugify(script['topic'])}"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "script.json").write_text(json.dumps(script, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"🧩 Plates: {script.get('format') or ' > '.join(s['plate'] for s in script['scenes'])}")
    print("🔊 Narration")
    dur, voice = audio_build.narrate(script)
    print(f"  {voice}, {dur:.1f}s")
    if dur > 170:
        raise RuntimeError(f"video would be {dur:.0f}s - too long for Shorts")
    env = env_with_tools()
    subprocess.run([sys.executable, str(BASE / "analysis" / "audio_vo.py")], cwd=BASE, env=env, check=True)
    print(f"🎬 Rendering 1080x1920 @ {FPS} fps (samples {SAMPLES})")
    raw = OUT / "raw.mp4"
    cmd = [tool("bun"), "scripts/render.ts", "video", "--fps", FPS, "--samples", SAMPLES, "--shutter", "0.5", "--crf", "18", "--out", str(raw)]
    if SAMPLES == "auto":
        cmd += ["--min-samples", "2", "--max-samples", "8"]
    t0 = time.time()
    subprocess.run(cmd, cwd=BASE / "app", env=env, check=True)
    print(f"  rendered in {time.time() - t0:.0f}s")
    print("🎵 Sound design")
    mixed = audio_build.mix(script)
    video = out_dir / "video.mp4"
    subprocess.run([audio_build.ffmpeg(), "-v", "error", "-y", "-i", str(raw), "-i", str(mixed), "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest", str(video)], check=True)
    raw.unlink(missing_ok=True)
    meta = {**script.get("youtube", {}), "instagram_caption": script.get("instagram_caption", ""), "topic": script["topic"],
            "duration": round(dur, 1), "voice": voice, "format": script.get("format"), "review": script.get("review")}
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"✅ {video} ({video.stat().st_size / 1e6:.1f} MB, {dur:.0f}s)")
    if show and Path(VLC).exists():
        subprocess.Popen([VLC, str(video)])
    return video, meta


def upload(video, meta, state):
    rec = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "topic": meta["topic"], "format": meta.get("format")}
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
            rec["instagram_id"] = upload_reel(video, meta["instagram_caption"])   # AI-info label
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
    args = ap.parse_args()
    if args.post and date.today().isoformat() > RUN_UNTIL:
        print(f"Posting window ended on {RUN_UNTIL}.")
        return 0
    state = load_state()
    topic = None
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
        print(f"📌 Topic: {topic}")
        try:
            script = writer.write_script(topic, state["used_formats"], seed=time.time_ns())
        except Exception:
            if args.post:                    # a topic that fails twice is skipped, so it can never block the queue
                failed[topic] = failed.get(topic, 0) + 1
                STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
            raise
        script["topic"] = script.get("topic") or topic
    video, meta = make_video(script, args.show)
    if not args.post:
        print("(local run - nothing posted, state unchanged)")
        return 0
    if topic and not args.topic:
        state["used_topics"].append(topic)
    state["used_formats"].append(script.get("format", ""))
    ok = upload(video, meta, state)
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
