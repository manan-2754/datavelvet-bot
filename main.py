"""
Motion Graphics Bot - premium 2D motion-graphics explainers. Every video gets its own format (scene layouts chosen
from the content, never the same sequence twice) and its own design DNA (palette, type, shapes, connectors, motion).

  python main.py                      # write + render one video in 4K (nothing posted)
  python main.py --preview --show     # 1080p, then open it in VLC
  python main.py --script out/x/script.json   # re-render an existing script
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).parent
try:
    from dotenv import load_dotenv
    load_dotenv(BASE / ".env", override=True)
except ImportError:
    pass

import mg  # noqa: E402
import style  # noqa: E402
from ui_sound import mix_screen  # noqa: E402
from voice import build_narration  # noqa: E402

OUTPUT = BASE / "out"
STATE = BASE / "state.json"
HANDLE = os.getenv("CHANNEL_HANDLE", "@datavelvet")
RUN_UNTIL = os.getenv("RUN_UNTIL") or "2027-02-08"
VLC = r"C:\Program Files\VideoLAN\VLC\vlc.exe"


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:50] or "video"


def load_state():
    st = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    for k in ("used_topics", "posts", "used_formats", "used_palettes", "used_combos", "used_signatures", "used_layout_seqs"):
        st.setdefault(k, [])
    return st


def make_video(script, dna, out_dir, preview=False):
    out_dir.mkdir(parents=True, exist_ok=True)
    pal = style.palette(dna["palette"], dna["rot"])
    (out_dir / "script.json").write_text(json.dumps({**script, "dna": dna}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"🎨 Design: {pal['name']} | fonts {style.FONT_PAIRS[dna['fonts']][0]} | "
          + ", ".join(f"{k}={dna[k]}" for k in style.OPTIONS))
    print(f"🧩 Format: {script.get('format') or ' > '.join(s['layout'] for s in script['scenes'])}")
    print("🔊 Narration")
    wav, durations, voice, words = build_narration(script["scenes"], out_dir / "audio")
    total = sum(durations)
    print(f"  voice: {voice}, total {total:.1f}s")
    if total > 178:
        raise RuntimeError(f"Video would be {total:.0f}s - over the 3 minute Shorts limit")
    w, h = (1080, 1920) if preview else (2160, 3840)
    video = mg.Video(script, durations, words, dna, w, h, 30, HANDLE)
    print("🎵 Sound design")
    gains = {"pop": 0.55, "tick": 0.35, "whoosh": 0.0}
    sfx = [(t, kind, gains[kind]) for t, kind in video.sound_events()]
    mixed = mix_screen(wav, sfx, video.total, out_dir / "audio" / "mix.wav", seed=dna["seed"] % 997, hook=True)
    print(f"🎬 Rendering {w}x{h}")
    out = out_dir / "video.mp4"
    mg.render(video, mixed, out)
    meta = {**script.get("youtube", {}), "instagram_caption": script.get("instagram_caption", ""),
            "topic": script["topic"], "duration": round(total, 1), "voice": voice, "palette": pal["name"],
            "format": script.get("format"), "dna": dna}
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    shutil.rmtree(out_dir / "audio", ignore_errors=True)
    print(f"✅ {out} ({out.stat().st_size / 1e6:.1f} MB, {total:.0f}s)")
    return out, meta


def upload(video, meta, state):
    from datetime import datetime, timezone
    rec = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "topic": meta["topic"],
           "palette": meta["palette"], "format": meta["format"]}
    ok = True
    if os.getenv("AUTO_POST_YOUTUBE", "false").lower() == "true":
        try:
            from youtube_upload import upload_video
            rec["youtube_id"] = upload_video(video, meta)
        except Exception as e:
            ok = False
            print(f"❌ YouTube upload failed: {e}")
    if os.getenv("AUTO_POST_INSTAGRAM", "false").lower() == "true":
        try:
            from instagram_upload import upload_reel
            rec["instagram_id"] = upload_reel(video, meta["instagram_caption"])
        except Exception as e:
            ok = False
            print(f"❌ Instagram upload failed: {e}")
    state["posts"].append(rec)
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", help="render this script JSON instead of writing a new one")
    ap.add_argument("--topic", help="override the next topic")
    ap.add_argument("--preview", action="store_true", help="1080p instead of 4K")
    ap.add_argument("--show", action="store_true", help="open the result in VLC")
    ap.add_argument("--post", action="store_true", help="upload after rendering (what the cloud job runs)")
    args = ap.parse_args()
    from datetime import date
    if args.post and date.today().isoformat() > RUN_UNTIL:
        print(f"Posting window ended on {RUN_UNTIL}.")
        return 0
    state = load_state()
    topic = None
    if args.script:
        script = json.loads(Path(args.script).read_text(encoding="utf-8"))
        dna = script.pop("dna", None) or style.new_dna(state)
    else:
        import writer
        topics = json.loads((BASE / "topics.json").read_text(encoding="utf-8"))
        fresh = [t for t in topics if t not in state["used_topics"]] or topics
        topic = args.topic or fresh[0]
        print(f"📌 Topic: {topic}")
        last = state["used_formats"][-1].count("|") + 1 if state["used_formats"] else None
        script = writer.write_script(topic, state["used_formats"], last, seed=time.time_ns())
        script["topic"] = script.get("topic") or topic
        dna = style.new_dna(state, seed=time.time_ns())
    out_dir = OUTPUT / f"{time.strftime('%Y%m%d-%H%M%S')}_{slugify(script['topic'])}"
    video, meta = make_video(script, dna, out_dir, args.preview)
    if args.show and Path(VLC).exists():
        subprocess.Popen([VLC, str(video)])
    if not args.post:
        print("(local run - nothing posted, state unchanged)")
        return 0
    if topic and not args.topic:
        state["used_topics"].append(topic)
    layouts = [s["layout"] for s in script["scenes"]]
    style.remember(state, dna, layouts)
    state["used_formats"].append(script.get("format") or "|".join(layouts))
    ok = upload(video, meta, state)
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
