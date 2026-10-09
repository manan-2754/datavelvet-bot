"""
3D Explainer Video Factory

topic -> Gemini storyboard -> per-scene narration with word timings -> 4K word-synced 3D diagram render
      -> (optional) upload to YouTube Shorts + Instagram Reels

Usage:
  python main.py                                  # make one video from the next topic
  python main.py --post                           # make one video and upload it (what the cloud job runs)
  python main.py --storyboard storyboards/x.json  # render a specific storyboard
  python main.py --preview                        # 1080p instead of 4K (much faster, for testing)
"""
import argparse
import json
import os
import re
import shutil
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

BASE = Path(__file__).parent
load_dotenv(BASE / ".env", override=True)

import analytics  # noqa: E402
import storyboard as sbm  # noqa: E402
from human import add_human_clips  # noqa: E402
from motion3d import THEMES, compile_scenes, render_motion  # noqa: E402
from sound import mix_audio  # noqa: E402
from voice import build_narration  # noqa: E402

OUTPUT = BASE / "output"
RUN_UNTIL = os.getenv("RUN_UNTIL") or "2027-02-08"      # stop posting after 4 months
HANDLE = os.getenv("CHANNEL_HANDLE", "")


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:50] or "video"


def make_video(sb, out_dir, preview=False, theme=None, series_label=""):
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "storyboard.json").write_text(json.dumps(sb, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n🔊 Narration")
    wav, durations, voice, word_times = build_narration(sb["scenes"], out_dir / "audio")
    total = sum(durations)
    print(f"  voice: {voice}, total {total:.1f}s")
    if total > 178:
        raise RuntimeError(f"Video would be {total:.0f}s - over the 3 minute Shorts limit")

    print("\n🎵 Music + sound effects")
    compiled, _ = compile_scenes(sb["scenes"], durations, word_times)
    mixed = mix_audio(wav, compiled, total, out_dir / "audio" / "final_mix.wav", seed=len(sb["topic"]),
                      hook=bool(sb.get("hook")))

    w, h = (1080, 1920) if preview else (2160, 3840)
    print(f"\n🎬 Rendering {w}x{h} (theme: {(theme or THEMES[0])['name']})")
    video = out_dir / "video.mp4"
    render_motion(sb["scenes"], durations, word_times, mixed, video, w, h, 30, HANDLE,
                  theme=theme, hook=sb.get("hook", ""), series_label=series_label)
    video = add_human_clips(video, w, h, seed=sb["topic"])

    meta = {**sb["youtube"], "instagram_caption": sb["instagram_caption"], "topic": sb["topic"],
            "duration": round(total, 1), "voice": voice, "resolution": f"{w}x{h}",
            "hook": sb.get("hook", ""), "series": sb.get("series", ""), "episode": sb.get("episode"),
            "theme": (theme or THEMES[0])["name"], "review": sb.get("review")}
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    shutil.rmtree(out_dir / "audio", ignore_errors=True)
    print(f"\n✅ {video} ({video.stat().st_size / 1e6:.1f} MB, {total:.0f}s)")
    return video, meta


def upload(video, meta, state):
    record = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "topic": meta["topic"],
              "series": meta.get("series"), "episode": meta.get("episode"), "hook": meta.get("hook"),
              "theme": meta.get("theme"), "duration": meta.get("duration")}
    ok = True
    if os.getenv("AUTO_POST_YOUTUBE", "false").lower() == "true":
        try:
            from youtube_upload import upload_video
            record["youtube_id"] = upload_video(video, meta)
        except Exception as e:
            ok = False
            print(f"❌ YouTube upload failed: {e}")
    if os.getenv("AUTO_POST_INSTAGRAM", "false").lower() == "true":
        try:
            from instagram_upload import upload_reel
            record["instagram_id"] = upload_reel(video, meta["instagram_caption"])
        except Exception as e:
            ok = False
            print(f"❌ Instagram upload failed: {e}")
    state["posts"].append(record)
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--storyboard", help="render this storyboard JSON instead of writing a new one")
    ap.add_argument("--topic", help="override the next topic")
    ap.add_argument("--preview", action="store_true", help="render 1080p instead of 4K")
    ap.add_argument("--post", action="store_true", help="upload after rendering")
    ap.add_argument("--series", choices=list(sbm.SERIES), help="force a series instead of letting the stats decide")
    args = ap.parse_args()

    if args.post and date.today().isoformat() > RUN_UNTIL:
        print(f"Posting window ended on {RUN_UNTIL} - nothing to do.")
        return 0

    state = sbm.load_state()
    print("📊 Channel stats")
    print(f"  updated {analytics.refresh_stats(state)} videos - {analytics.summary(state)}")
    series = args.series or analytics.pick_series(state)
    episode = state.setdefault("series_counts", {}).get(series, 0) + 1
    bank_name = None
    if args.storyboard:
        sb = sbm.validate(json.loads(Path(args.storyboard).read_text(encoding="utf-8")))
    else:
        topic = args.topic or sbm.next_topic(state)
        print(f"📌 Topic: {topic}  |  series: {series} #{episode}")
        try:
            sb = sbm.write_storyboard(topic, series=series, insights=analytics.insights_text(state))
            sb["topic"] = sb.get("topic") or topic
        except Exception as e:
            print(f"⚠️  Gemini failed ({e}) - using a hand-written storyboard")
            bank_name, sb = sbm.bank_storyboard(state)
            if not sb:
                print("❌ No storyboard available - skipping this run")
                return 1
        if not args.topic and not bank_name:
            state["used_topics"].append(topic)
    if bank_name:
        state["used_bank"].append(bank_name)

    # series branding + variety
    sb["series"], sb["episode"] = series, episode
    base_title = re.sub(r"\s*#shorts\s*$", "", sb["youtube"]["title"], flags=re.I)
    for name in sbm.SERIES:   # Gemini sometimes adds the series itself - we add it below
        base_title = re.sub(rf"\s*[\(\[|:-]*\s*{re.escape(name)}\s*[\)\]]?", "", base_title, flags=re.I).strip(" |:-")
    sb["youtube"]["title"] = f"{base_title[:62]} | {series} #{episode} #shorts"
    sb["instagram_caption"] = f"{series} · Ep {episode}\n\n" + sb["instagram_caption"]
    theme = THEMES[len(state.get("posts", [])) % len(THEMES)]
    label = f"{series.upper()} · EP {episode:02d}"

    out_dir = OUTPUT / f"{time.strftime('%Y%m%d-%H%M%S')}_{slugify(sb['topic'])}"
    video, meta = make_video(sb, out_dir, args.preview, theme=theme, series_label=label)

    if not args.post:
        print("\n(local run - nothing posted, topic queue unchanged)")
        return 0
    state["series_counts"][series] = episode
    ok = upload(video, meta, state)
    sbm.save_state(state)
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
