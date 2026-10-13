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
from datetime import date, datetime, timedelta, timezone
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
import covers  # noqa: E402
import critic  # noqa: E402
import links  # noqa: E402
import longform  # noqa: E402
import research  # noqa: E402
import trends  # noqa: E402
import viewer_questions  # noqa: E402
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


def add_links(script, state):
    """Affiliate links matched to the topic + a pointer to the latest long-form compilation."""
    chosen = links.apply(script)
    if chosen:
        print(f"🔗 Links: {', '.join(ln.get('name') or ln['url'] for ln in chosen)}")
    comp = None if script.get("long") else ((longform.load_long()["videos"] or [{}])[-1].get("youtube_id"))
    if comp:
        yt = script.setdefault("youtube", {})
        yt["description"] = (f"▶ Full episode (8-10 min deep dive): https://youtu.be/{comp}\n\n" + yt.get("description", ""))[:4900]
    script["links_done"] = True


def pick_variants(script, state):
    """A/B: choose the title style and cover style, weighted by what has performed best so far (25% exploration)."""
    rnd = random.SystemRandom()
    tv = script.get("title_variants") or {}
    if len(tv) == 2:
        styles = list(tv)
        style = rnd.choice(styles) if rnd.random() < 0.25 else max(styles, key=lambda k: analytics.weight(state, "title", k) + rnd.random() * 0.01)
        script.setdefault("youtube", {})["title"] = tv[style]
        script["title_style"], script["title_alt"] = style, tv[[k for k in styles if k != style][0]]
    covers_ = ["band", "bold"]
    script["cover_style"] = rnd.choice(covers_) if rnd.random() < 0.25 else max(covers_, key=lambda k: analytics.weight(state, "cover", k) + rnd.random() * 0.01)
    print(f"  A/B title: {script.get('title_style')} | cover: {script['cover_style']}")


def swap_weak_titles(state):
    """24 h check: a Short far below the channel's usual views gets its other title (YouTube allows title edits)."""
    posts = [p for p in state.get("posts", []) if p.get("youtube_id")]
    views = sorted((p.get("stats") or {}).get("yt_views", 0) for p in posts[-12:] if (p.get("stats") or {}).get("yt_views") is not None)
    if len(views) < 4:
        return
    median = views[len(views) // 2]
    for p in posts[-6:]:
        v = (p.get("stats") or {}).get("yt_views")
        if not p.get("title_alt") or p.get("title_swapped") or v is None or not (20 <= analytics._age_h(p) <= 60) or v >= 0.6 * median:
            continue
        try:
            from googleapiclient.discovery import build
            from youtube_upload import get_credentials
            api = build("youtube", "v3", credentials=get_credentials(), cache_discovery=False)
            sn = api.videos().list(part="snippet", id=p["youtube_id"]).execute()["items"][0]["snippet"]
            api.videos().update(part="snippet", body={"id": p["youtube_id"], "snippet": {"title": p["title_alt"][:100], "description": sn.get("description", ""),
                                                                                           "tags": sn.get("tags", []), "categoryId": sn.get("categoryId", "28")}}).execute()
            p["title_swapped"] = True
            print(f"  retitled {p['youtube_id']} ({v} views vs median {median}): {p['title_alt'][:60]}")
        except Exception as e:
            print(f"  title swap skipped ({str(e)[:100]})")


def features(script, meta):
    st = script.get("style") or {}
    d = meta.get("duration") or 0
    return {"angle": script.get("angle"), "layouts": (script.get("format") or "").split(" > "),
            "types": sorted({e.get("type") for s in script["scenes"] for e in (s.get("data") or {}).get("elements", []) if e.get("type")}),
            "cams": [(s.get("data") or {}).get("camera") for s in script["scenes"] if (s.get("data") or {}).get("camera")],
            "hue": (st.get("name") or "").split(" ")[0], "voice": meta.get("voice"), "music": (script.get("music") or "").split(" ")[0],
            "length": "short" if d < 50 else ("mid" if d < 75 else "long"), "level": script.get("level"),
            "trend": bool(script.get("trend")), "series": (script.get("series") or {}).get("name"), "cta": script.get("cta_kind"),
            "fmt": "viewer" if script.get("viewer_q") else script.get("format_kind"),
            "title": script.get("title_style"), "cover": script.get("cover_style")}


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
    if script["scenes"] and script["scenes"][0].get("plate") == "world" and not voice:
        import pro
        dur, voice = pro.fit_narration(script)
        (out_dir / "script.json").write_text(json.dumps(script, indent=2, ensure_ascii=False), encoding="utf-8")
    else:
        dur, voice = audio_build.narrate(script, voice)
    print(f"  {voice}, {dur:.1f}s")
    if dur > 180 and not script.get("long"):
        raise RuntimeError(f"video would be {dur:.0f}s - too long for Shorts")
    env = env_with_tools()
    subprocess.run([sys.executable, str(BASE / "analysis" / "audio_vo.py")], cwd=BASE, env=env, check=True)
    print("🧐 " + critic.review(env, tool, land=bool(script.get("long"))))
    return {"out_dir": str(out_dir), "dur": dur, "voice": voice}


def render_range(out, frm=None, to=None, land=False):
    """Render the whole video, or one frame-exact slice of it (split rendering across cloud machines)."""
    env = env_with_tools()
    cmd = [tool("bun"), "scripts/render.ts", "video", "--fps", FPS, "--samples", SAMPLES, "--shutter", "0.5", "--crf", "18", "--out", str(out)]
    if land:
        cmd += ["--land"]
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
    render_range(raw, land=bool(script.get("long")))
    return finish_video(script, ctx, raw, show)


def finish_video(script, ctx, raw, show=False):
    out_dir, dur, voice = Path(ctx["out_dir"]), ctx["dur"], ctx["voice"]
    out_dir.mkdir(parents=True, exist_ok=True)
    print("🎵 Sound design")
    mixed = audio_build.mix(script)
    if script.get("long"):
        print("📑 Chapters: " + " | ".join(longform.describe(script)))
    video = out_dir / "video.mp4"
    subprocess.run([audio_build.ffmpeg(), "-v", "error", "-y", "-i", str(raw), "-i", str(mixed), "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest", str(video)], check=True)
    raw.unlink(missing_ok=True)
    meta = {**script.get("youtube", {}), "instagram_caption": script.get("instagram_caption", ""), "topic": script["topic"],
            "duration": round(dur, 1), "voice": voice, "format": script.get("format"), "seed": script.get("seed"),
            "style_name": (script.get("style") or {}).get("name"), "angle": script.get("angle"),
            "review": script.get("review"), "music": script.get("music"), "sources": script.get("sources", []),
            "cover_ms": cover_ms(), "title_alt": script.get("title_alt"), "title_style": script.get("title_style"), "comment": script.get("comment") or "Did you know this before watching? Yes or no 👇", "series_name": (script.get("series") or {}).get("name")}
    meta["features"] = features(script, meta)
    try:                                       # designed Reel cover + carousel slides, from this video
        meta["cover_path"], meta["carousel"] = covers.make_all(video, script, out_dir)
        print(f"🖼️ Cover + {len(meta['carousel'])}-slide carousel ready")
    except Exception as e:
        print(f"  cover/carousel skipped ({e})")
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"✅ {video} ({video.stat().st_size / 1e6:.1f} MB, {dur:.0f}s)")
    if show and Path(VLC).exists():
        subprocess.Popen([VLC, str(video)])
    return video, meta


def upload(video, meta, state):
    rec = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "topic": meta["topic"], "format": meta.get("format"),
           "seed": meta.get("seed"), "features": meta.get("features"), "title_alt": meta.get("title_alt"), "title_style": meta.get("title_style")}
    ok = True
    if os.getenv("AUTO_POST_YOUTUBE", "false").lower() == "true":
        try:
            from youtube_upload import upload_video
            rec["youtube_id"] = upload_video(video, meta)              # marked as AI / synthetic content
            try:                                                       # first comment + series playlist
                from youtube_upload import add_to_playlist, post_comment
                post_comment(rec["youtube_id"], meta.get("comment"))
                sn = meta.get("series_name") or "Tech Explained"
                add_to_playlist(rec["youtube_id"], sn, f"DataVelvet 3D explainers - {sn}, one concept per Short.")
            except Exception as e:
                print(f"  YouTube comment/playlist skipped ({e})")
        except Exception as e:
            ok = False
            print(f"❌ YouTube upload failed: {e}")
    if os.getenv("AUTO_POST_INSTAGRAM", "false").lower() == "true":
        try:
            from instagram_upload import upload_reel
            rec["instagram_id"] = upload_reel(video, meta["instagram_caption"], meta.get("cover_ms"), cover=meta.get("cover_path"))   # AI-info label
            try:
                from instagram_upload import post_comment as ig_comment
                ig_comment(rec["instagram_id"], meta.get("comment"))
            except Exception as e:
                print(f"  Instagram comment skipped ({e})")
            if meta.get("carousel") and len(state["posts"]) % 6 == 2:     # a Reel-based carousel every other day (plus the daily lane)
                try:
                    from instagram_upload import upload_carousel
                    title = covers.clean_title({"youtube": {"title": meta.get("title")}, "topic": meta.get("topic")})
                    cap = (f"{title} 👉 swipe through it, then save it for later.\n\n" + meta["instagram_caption"])[:2150]
                    rec["carousel_id"] = upload_carousel(meta["carousel"], cap)
                except Exception as e:
                    print(f"  Instagram carousel skipped ({e})")
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
    ap.add_argument("--long", action="store_true", help="an 8-10 min landscape long-form YouTube video (chapters)")
    args = ap.parse_args()
    if args.stage == "render":
        return stage_render(args.chunk)
    if args.stage == "finish":
        return stage_finish(args.post)
    if args.post and not args.long and os.getenv("SLOT_TARGET"):   # this slot was already covered (e.g. a manual post)
        from zoneinfo import ZoneInfo
        hh, mm = map(int, os.environ["SLOT_TARGET"].split(":"))
        target = datetime.now(ZoneInfo("America/Toronto")).replace(hour=hh, minute=mm, second=0, microsecond=0)
        last = next((p.get("time") for p in reversed(load_state().get("posts", [])) if p.get("time")), None)
        if last and datetime.fromisoformat(last) > target - timedelta(hours=3):
            print(f"⏭️ A video was already posted for the {os.environ['SLOT_TARGET']} ET slot - skipping to avoid a double post")
            gh_output(has_video="false", chunks="[]")
            return 0
    if args.post and date.today().isoformat() > RUN_UNTIL:
        print(f"Posting window ended on {RUN_UNTIL}.")
        gh_output(has_video="false", chunks="[]")
        return 0
    state = load_state()
    if args.long:
        return run_long(args, state)
    art_director.prune(state)          # styles posted more than 3 hours ago are forgotten
    try:                               # the learning loop: fresh stats -> what works -> next script
        n = analytics.collect(state)
        if args.post:
            swap_weak_titles(state)
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
        if os.getenv("PRO_STYLE", "1") != "0" and not args.topic:      # deep dives use the developer topic list
            deep = json.loads((BASE / "topics_deep.json").read_text(encoding="utf-8"))
            topic = ([t for t in deep if t not in state["used_topics"] and failed.get(t, 0) < 2] or deep)[0]
        trend = None
        if not args.topic and os.getenv("PRO_STYLE", "1") == "0" and (args.trend or (args.post and len(state["posts"]) % 3 == 1)):
            trend = trends.pick(set(state["used_topics"]) | set(topics), writer.llm)
            if trend:
                topic = trend["topic"]
                print(f"🔥 Trending topic: {topic}  ({trend['why']})")
        if not args.topic and os.getenv("PRO_STYLE", "1") != "0" and (args.trend or (args.post and len(state["posts"]) % 3 == 1)):
            import pro
            trend = pro.trend_topic(set(state["used_topics"]) | set(json.loads((BASE / "topics_deep.json").read_text(encoding="utf-8"))))
            if trend:
                topic = trend["topic"]
                print(f"🔥 Trending tech topic: {topic}  ({trend['why']})")
        vq = None
        if args.post:                          # viewers' questions from the comments become videos
            try:
                n = viewer_questions.collect(state, writer.llm)
                print(f"🙋 Viewer questions: {n} new, {len(state.get('viewer_questions', []))} queued")
            except Exception as e:
                print(f"  viewer questions skipped ({e})")
        if not args.topic and not trend and state.get("viewer_questions") and os.getenv("PRO_STYLE", "1") == "0":
            vq = state["viewer_questions"].pop(0)
            topic = vq["topic"]
            print(f"🙋 Answering {vq['user']} ({vq['platform']}): {vq['text'][:80]}")
        print(f"📌 Topic: {topic}")
        facts = research.gather(topic, llm=writer.llm)
        print(f"📚 Research: {len(facts['sources'])} source(s)  {' '.join(facts['sources'])}")
        series = series_info(topic, state, fresh)
        level = pick_level(state)
        mode = composer.length_mode(state)
        print(f"⏱️ Length: {mode} (hook-first)")
        print(f"🎞️ Series: {series['name']} · EP {series['ep']} · level {level}" + (f"  (next: {series['next']})" if series.get("next") else ""))
        try:
            angle = art_director.pick_angle(state)
            print(f"🎬 Angle: {angle[0]}  (every scene composed from scratch)")
            script = None
            if os.getenv("PRO_STYLE", "1") != "0":     # pro story: one running example, real UI objects, live pages, 3D world
                try:
                    import pro
                    script = pro.script_for(topic, facts, banned=state.get("scene_signatures", []))
                    pick_variants(script, state)
                    script.update(series=series, level=level, trend=trend, viewer_q=vq)
                    add_sources(script, facts["sources"] + ((trend or {}).get("sources") or []))
                except Exception as e:
                    script = None
                    print(f"  pro story failed ({str(e)[:120]}) - using the classic composer for this slot")
            if script is None:
              try:
                  script = composer.write(topic, banned=state.get("scene_signatures", []) + longform.load_long()["scene_signatures"], recent=state.get("compose_formats", []),
                                          angle=angle, seed=time.time_ns(), facts=facts, hints=analytics.hints(state) + (viewer_questions.hint(vq) if vq else ""), level=level,
                                          series=series, mode=mode, plain=bool(vq))
                  script.update(series=series, level=level, trend=trend, viewer_q=vq)
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
    if not args.script and not script.get("links_done"):
        add_links(script, state)
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


def run_long(args, state):
    """The 8-10 min landscape video: outline -> chapters composed from scratch -> fresh genome -> narration."""
    every = float(os.getenv("LONG_EVERY_DAYS") or 3)
    vids = longform.load_long()["videos"]
    if args.post and not args.script and vids:       # one long video every N days (the workflow checks daily)
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(vids[-1]["time"])).total_seconds() / 86400
        if age < every - 0.5:
            print(f"Last long-form video was {age:.1f} days ago - the next one is due after {every:g} days")
            gh_output(has_video="false", chunks="[]")
            return 0
    art_director.prune(state)
    script = json.loads(Path(args.script).read_text(encoding="utf-8")) if args.script else         longform.write(state, longform.load_long(), topic=args.topic)
    script["long"] = True
    script["seed"] = script.get("seed") or pick_seed(state)
    script["style"] = script.get("style") or art_director.new_genome(state, len(script["scenes"]))
    if not script.get("links_done"):
        add_links(script, state)
    if args.stage == "prepare":
        ctx = prepare_video(script)
        parts = chunks(int(os.getenv("RENDER_CHUNKS", "20")))
        BUNDLE.write_text(json.dumps({"script": script, "ctx": ctx, "topic": script["topic"], "topic_override": True, "chunks": parts},
                                     ensure_ascii=False), encoding="utf-8")
        gh_output(has_video="true", chunks=json.dumps(list(range(len(parts)))))
        print(f"📦 Bundle ready: {len(parts)} slices of ~{ctx['dur'] / len(parts):.1f}s")
        return 0
    video, meta = make_video(script, args.show)
    if not args.post:
        print("(local run - nothing posted)")
        return 0
    return publish(script, video, meta, state, None, True)


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
    render_range(out, frm, to, land=bool(b["script"].get("long")))
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
    if script.get("long"):                     # long-form: YouTube only, its own state file
        from youtube_upload import upload_video
        thumb = Path(video).parent / "thumb.jpg"
        subprocess.run([audio_build.ffmpeg(), "-v", "error", "-y", "-ss", f"{(meta.get('cover_ms') or 1500) / 1000:.2f}", "-i", str(video),
                        "-frames:v", "1", "-vf", "scale=1280:720", "-q:v", "3", str(thumb)], check=False)
        if os.getenv("AUTO_POST_YOUTUBE", "false").lower() != "true":
            print("AUTO_POST_YOUTUBE is off - not uploading")
            return 0
        vid = upload_video(video, meta, thumbnail=thumb if thumb.exists() else None)
        try:
            from youtube_upload import add_to_playlist, post_comment
            ch = script.get("chapters") or []
            post_comment(vid, script.get("comment") or (f"Which part surprised you most - {ch[1]} or {ch[-2]}? 👇" if len(ch) > 3 else
                                                         "What should the next deep dive explain? 👇"))
            add_to_playlist(vid, "Deep Dives: 8-10 Minute Explainers", "Full 3D deep dives, one big topic per video, with chapters.")
        except Exception as e:
            print(f"  YouTube comment/playlist skipped ({e})")
        ls = longform.load_long()
        longform.remember(ls, script, vid)
        longform.save_long(ls)
        return 0
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
