"""
Pro bot: "how it REALLY works" story Shorts in the style of the best tech explainers - one running example followed
through every stage, a HUD (stage stepper + live counter), 2-4 word phrase captions with a highlighted key word,
realistic UI mockups (terminal, code, browser, tables, chat, metrics, comparisons, flows) on every beat, a 3D
hologram hero for depth, fast cuts, and a final summary of the whole journey. Never posts by itself.

  python pro.py --topic "What happens when you send a WhatsApp message" --show
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
from pathlib import Path

BASE = Path(__file__).resolve().parent
try:
    from dotenv import load_dotenv
    load_dotenv(BASE / ".env" if (BASE / ".env").exists() else BASE.parent / "kit-bot" / ".env", override=True)
except ImportError:
    pass

import art_director  # noqa: E402
import audio_build  # noqa: E402
import research  # noqa: E402
import writer  # noqa: E402

MAX_SECONDS = 90                      # 1:30 cap
MAX_WORDS = 190                       # ~140 words a minute (the live bot's pace) + pauses = under 90 s
KINDS = ["scene", "terminal", "code", "browser", "table", "chat", "phone", "request", "stack", "metric", "compare", "flow", "checklist", "summary"]
VLC = r"C:\Program Files\VideoLAN\VLC\vlc.exe"
MAX_SECONDS = 90                      # 1:30 cap
MAX_WORDS = 190                       # ~140 words a minute (the live bot's pace) + pauses = under 90 s
PROMPT = """You write a premium "how it REALLY works" YouTube Short / Instagram Reel for "DataVelvet" (everyday people,
3D tech explainers). Topic: "{topic}"
{facts}
Style (what the best tech explainers do):
- ONE running example followed through every step (e.g. "you type 'hi' to ChatGPT", "you tap Pay on your phone").
- 5-7 STAGES of the journey (max 12 chars each), in order. Every beat belongs to one stage.
- 13-16 BEATS, 170-190 words in total (the video must stay under 90 seconds). Each beat = ONE spoken sentence of 8-14 words, plain everyday words, specific and surprising, with
  real numbers where known (ms, km, how many, how big). Beat 1 is a scroll-stopping hook. The last beat recaps the
  whole journey and ask viewers one question to comment on.
- Each beat gets ITS OWN VISUAL, designed from scratch for exactly what that sentence says. Mostly use
  "scene" (a free composition you design): {{"kind": "scene", "elements": 2-6 {{"id", "type", "x": 0-100, "y": 0-100,
  "size": "S"|"M"|"L", "label": max 18 chars, "sub": max 22 chars, "color": "emerald"|"blue"|"amber"|"cyan"|"violet"|"rose"|"white",
  "count", "items": [...], "value", "translate", "enter": "pop"|"drop"|"slide"|"zoom"|"unfold", "motion": "float"|"pulse"|"spin"|"none",
  "at": 0-0.8 (when it pops in, as a fraction of the beat)}}, "links": 0-5 {{"from": id, "to": id, "label": max 14 chars, "color"}}}}.
  Element types: cylinder (database, "count" = rings), stack (isometric layers, "items" = layer names bottom first),
  tower (server/console), orbit (a core with "count" avatars/icons orbiting it in 3D, "items" = their names), node (service/UI card),
  code ("items" = 2-5 code lines typed live, OR "translate": {{"from_lang", "to_lang", "from": [lines], "to": [lines]}} morphing
  one language into another), metric ("value": e.g. "4.2 ms", label = what it is), avatars ("items" = first names), globe,
  gauge ("value": 0-1), queue ("items" = what is waiting), bars ("items" = numbers), lock, cloud, file, user, chip, phone, badge.
  Links draw themselves and carry glowing packets - use them for anything that FLOWS (requests, data, replication, keys).
  Lay elements out so they never overlap (spread x/y), stagger "at" so something new appears every ~1-2 seconds,
  and make EVERY beat's composition different (different types, positions, links) - never reuse a layout.
  Occasionally (at most 3 beats) you may instead use a realistic mockup when it IS the point: phone {{"app", "messages"}},
  table {{"query", "columns", "rows", "marks"}}, request {{"method", "url", "status", "ms", "lines"}}, terminal {{"lines"}} or
  code {{"title", "lang", "lines"}} (terminal + code together at most 2 beats per video), checklist, compare, metric.
  The final recap beat: summary {{"items": the stages in order}}.
  Keep the SAME running example's data everywhere (same names, ids, numbers).
- LIVE INTERNET: at most ONE beat may add "site": a real public https page, and only if showing that real page is the point
  of the sentence (e.g. the actual RFC or official doc). Most videos should have none.
- REAL PHOTO: at most ONE beat may add "photo": a short Wikimedia Commons query for a real photo of a physical thing
  (e.g. "submarine communications cable"). Most beats should be designed scenes instead.
{banned}- "key": 1-2 words copied EXACTLY from the beat's sentence to highlight.
- "object": a 3D object for the beat's stage, one of {objects}.
- A running "counter" that grows along the journey (e.g. elapsed ms, km travelled, bytes) - give its value per beat.
Accurate facts only; never invent statistics; no emojis; no "in this video".
Return ONLY JSON:
{{"title": max 60 chars, "example": the running example (max 34 chars), "stages": [...], "counter": {{"label": e.g. "T+",
 "unit": e.g. "ms"}}, "beats": [{{"stage": index, "line": "...", "key": "...", "object": "...", "counter": number,
 "widget": {{"kind": "...", ...}}}}], "youtube": {{"title": max 70 chars ending " #shorts", "description": 2 sentences + 5
 hashtags, "tags": [6-8]}}, "instagram_caption": 2 lines + "Save this for later." + 6 hashtags, "comment": one question}}
{feedback}"""


def signature(w):
    """Layout fingerprint of one beat's visual (types + coarse positions + links) - never reused across videos."""
    w = w if isinstance(w, dict) else {}
    if w.get("kind") != "scene":
        return f"{w.get('kind')}:{len(w.get('lines') or w.get('rows') or w.get('messages') or w.get('items') or [])}"
    els = [e for e in (w.get("elements") or []) if isinstance(e, dict)]
    def cell(v):
        try:
            return min(2, int(float(v) // 34))
        except (TypeError, ValueError):
            return 1
    parts = sorted(f"{e.get('type')}@{cell(e.get('x', 50))},{cell(e.get('y', 50))}" for e in els)
    return "|".join(parts) + f"/L{len(w.get('links') or [])}"



STORY_MODEL = "claude-sonnet-5-5"   # the premium story is written by a stronger model than the old Shorts


def _story_llm(prompt):
    """Sonnet first (better facts and pacing), then the shared fallback chain."""
    try:
        text = writer._claude_call(prompt, model=STORY_MODEL)
        print(f"  pro story by Claude / {STORY_MODEL}")
        return writer._json_text(text)
    except Exception as e:
        print(f"  {STORY_MODEL}: {str(e)[:120]} - using the fallback chain")
        return writer.llm(prompt, label="pro story")


def write_story(topic, facts=None, banned=()):
    facts = facts or research.gather(topic, llm=writer.llm)
    ftxt = (f"REFERENCE FACTS (from {', '.join(facts['sources'][:3])}) - use their numbers:\n{facts['facts'][:3500]}") if facts.get("facts") else ""
    fb = ""
    for attempt in range(4):
        ban = ("- These scene layouts were already used in earlier videos - do NOT reproduce any of them:\n  " + "\n  ".join(list(banned)[-60:])) if banned else ""
        st = json.loads(_story_llm(PROMPT.format(topic=topic, facts=ftxt, objects=", ".join(writer.OBJECTS), feedback=fb, banned=ban)))
        beats = [b for b in (st.get("beats") or []) if isinstance(b, dict) and len(str(b.get("line", "")).split()) >= 4]
        stages = [str(s)[:12] for s in (st.get("stages") or [])][:7]
        words = sum(len(str(b['line']).split()) for b in beats)
        if len(beats) < 11 or len(stages) < 4 or words > MAX_WORDS:
            fb = f"\nThe previous draft had {len(beats)} beats, {words} words and {len(stages)} stages - give 13-16 beats, at most {MAX_WORDS} words in total, and 5-7 stages." + ("\nPREVIOUS DRAFT (shorten it, keep the best beats):\n" + json.dumps(st, ensure_ascii=False)[:9000] if words > MAX_WORDS else "")
            continue
        sigs = [signature(b.get("widget")) for b in beats]
        seen, clash = set(banned), []
        for i, g in enumerate(sigs):
            if "@" in g and g in seen:
                clash.append(i + 1)
            seen.add(g)
        n_scene = sum(1 for b in beats if (b.get("widget") or {}).get("kind") == "scene")
        if (clash or n_scene < len(beats) * 0.6) and attempt < 3:
            fb = (f"\nRedesign: beats {clash} reuse a layout that already exists" if clash else "\nRedesign:") + (f"; only {n_scene} of {len(beats)} beats are designed scenes - make at least 70% of beats 'scene' compositions" if n_scene < len(beats) * 0.6 else "") + ". Keep the same lines.\nPREVIOUS DRAFT:\n" + json.dumps(st, ensure_ascii=False)[:9000]
            print(f"  redesign asked (clashes {clash}, {n_scene}/{len(beats)} scenes)")
            continue
        sc = {"topic": topic, "scenes": [{"plate": "story", "title": stages[min(len(stages) - 1, int(b.get("stage") or 0))],
                                          "lines": [b["line"]], "data": {"widget": b.get("widget")}} for b in beats]}
        rv = writer.review(sc)
        print(f"  fact-check: {rv['score']}/10, {len(rv['critical'])} real error(s)")
        for c in rv["critical"]:
            print(f"    - {c[:160]}")
        if not rv["critical"] and rv["score"] >= 7:
            st["beats"], st["stages"], st["sources"] = beats, stages, facts["sources"]
            return st
        # revise the same draft instead of starting over - it converges much faster
        fb = ("\nHere is your previous draft. A fact-checker rejected it. Return the SAME story with every point fixed "
              "(remove or soften any claim you cannot be sure of; prefer well-known, verifiable numbers):\n- "
              + "\n- ".join(rv["critical"] + rv["minor"]) + "\nPREVIOUS DRAFT:\n" + json.dumps(st, ensure_ascii=False)[:9000])
    raise RuntimeError("no story passed the fact-check")


BIG = re.compile(r"\b(million|billion|trillion|thousands?|millions|billions)\b|\b\d{1,3}(,\d{3})+\b|\b\d{4,}\b", re.I)


def pick_swarms(beats, most=3):
    """Beats with huge numbers get the swarm moment (thousands of data chips); never two in a row."""
    out = []
    for i, b in enumerate(beats):
        if len(out) < most and BIG.search(str(b.get("line", ""))) and not re.search(r"\b(19|20)\d\d\b", str(b.get("line", ""))) and (not out or i - out[-1] > 2):
            out.append(i)
    if not out:                                                     # every video gets at least one swarm moment
        k = next((i for i, b in enumerate(beats) if i > 1 and (b.get("widget") or {}).get("kind") in ("metric", "compare")), min(3, len(beats) - 1))
        out.append(k)
    return set(out)


def gesture(i, n, line, kind):
    """The presenter's body language for a beat."""
    if i == 0:
        return "wave"
    if i == n - 1:
        return "thumbs"
    if line.rstrip().endswith("?"):
        return "shrug" if i % 2 else "think"
    if kind in ("browser", "photo", "metric", "compare", "table"):
        return "point"
    return ["explain", "point", "idle", "explain", "think"][i % 5]


def capture_photos(st, most=1):
    """Real, freely-licensed photos from Wikimedia Commons (with credit) for beats that ask for one."""
    shots = BASE / "app" / "public" / "shots"
    shots.mkdir(parents=True, exist_ok=True)
    import requests
    ua = {"User-Agent": "DataVelvetProBot/1.0 (educational explainer videos)"}
    n = 0
    for i, b in enumerate(st["beats"]):
        q = str(b.get("photo") or "").strip()
        if not q or b.get("shot") or n >= most:
            continue
        try:
            r = requests.get("https://commons.wikimedia.org/w/api.php", headers=ua, timeout=20, params={
                "action": "query", "format": "json", "generator": "search", "gsrsearch": f"filetype:bitmap {q}", "gsrnamespace": 6, "gsrlimit": 12,
                "prop": "imageinfo", "iiprop": "url|size|extmetadata", "iiurlwidth": 1400}).json()
            pages = sorted((r.get("query") or {}).get("pages", {}).values(), key=lambda p: p.get("index", 99))
            for pg in pages:
                ii = (pg.get("imageinfo") or [{}])[0]
                md = ii.get("extmetadata") or {}
                lic = re.sub("<[^>]+>", "", (md.get("LicenseShortName") or {}).get("value", ""))
                if ii.get("width", 0) < 900 or not re.search(r"CC|Public domain|PD", lic, re.I) or re.search(r"non-?free|fair use", lic, re.I):
                    continue
                img = requests.get(ii.get("thumburl") or ii["url"], headers=ua, timeout=30)
                if img.status_code != 200 or not img.headers.get("content-type", "").startswith("image/"):
                    continue
                f = shots / f"p{i}.jpg"
                f.write_bytes(img.content)
                artist = re.sub("<[^>]+>", "", (md.get("Artist") or {}).get("value", "")).strip()[:40]
                b["pic"], b["credit"] = f"shots/p{i}.jpg", f"Photo: {artist or 'Wikimedia Commons'} · {lic} · Wikimedia Commons"
                n += 1
                print(f"  📷 real photo for beat {i + 1}: {pg.get('title', '')[:60]} ({lic})")
                break
        except Exception as e:
            print(f"  photo skipped ({q}): {str(e)[:80]}")
    return n


def render_parallel(env, raw, workers):
    """Split the video into frame-exact slices, render them side by side (each its own headless Chrome), stitch."""
    dur = json.loads((BASE / "data" / "audio.json").read_text(encoding="utf-8"))["duration"]
    fps, total = 30, round(json.loads((BASE / "data" / "audio.json").read_text(encoding="utf-8"))["duration"] * 30)
    b = [round(k * total / workers) for k in range(workers + 1)]
    parts = [(b[k] / fps, b[k + 1] / fps if k < workers - 1 else dur) for k in range(workers) if b[k + 1] > b[k]]
    files = [BASE / "out" / f"part{k:02d}.mp4" for k in range(len(parts))]
    procs = [subprocess.Popen([tool("bun"), "scripts/render.ts", "video", "--fps", str(fps), "--samples", "3", "--shutter", "0.9", "--crf", "18",
                               "--url", "http://localhost:1", "--from", f"{a:.6f}", "--to", f"{z:.6f}", "--noaudio", "--out", str(f)],
                              cwd=BASE / "app", env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) for (a, z), f in zip(parts, files)]
    print(f"  {len(procs)} render workers in parallel")
    bad = [k for k, p in enumerate(procs) if p.wait() != 0 or not files[k].exists()]
    if bad:
        raise RuntimeError(f"render slices failed: {bad}")
    lst = BASE / "out" / "parts.txt"
    lst.write_text("".join(f"file '{f.as_posix()}'\n" for f in files), encoding="utf-8")
    subprocess.run([audio_build.ffmpeg(), "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(raw)], check=True)
    for f in files:
        f.unlink(missing_ok=True)


def to_script(st):
    """Story JSON -> engine script: one 'story' scene per beat, sharing the stages, example and counter HUD."""
    scenes, prev = [], 0
    ctr = st.get("counter") or {}
    swarms = pick_swarms(st["beats"])
    look = random.Random(f"{st.get('title', '')}|{time.time_ns()}")                  # one palette per video: accent + presenter hoodie
    tint = look.choice(["#00F0FF", "#10B981", "#F59E0B", "#3B82F6", "#8B5CF6", "#F43F5E"])  # neon accents on the dark stage
    world = {"layout": look.choice(["line", "zigzag", "arc", "spiral", "stairs"]), "gap": look.random(), "camR": round(look.uniform(8.6, 10.6), 2),
             "camH": round(look.uniform(2.9, 4.6), 2), "fov": look.choice([32, 34, 36, 38, 40]), "push": round(look.uniform(0.7, 1.6), 2),
             "ambient": look.choice(["rings", "particles", "beams"]), "floor": look.choice(["dots", "lines", "cross"])}
    outfit = look.choice(["#5B3FD6", "#1F7A5C", "#C2410C", "#1E40AF", "#9D174D", "#334155"])
    for i, b in enumerate(st["beats"]):
        stage = max(0, min(len(st["stages"]) - 1, int(b.get("stage") or 0)))
        wd = b.get("widget") if isinstance(b.get("widget"), dict) else {}
        if wd.get("kind") not in KINDS:
            wd = {"kind": "checklist", "items": [b.get("key") or st["stages"][stage]]}
        try:
            val = float(b.get("counter"))
        except (TypeError, ValueError):
            val = None
        data = {"stages": st["stages"], "stage": stage, "example": st.get("example", ""), "key": str(b.get("key") or ""), "widget": wd,
                "object": b.get("object") if b.get("object") in writer.OBJECTS else random.choice(["phone", "server", "globe", "chip", "router"]),
                "light": False}
        if val is not None:
            data["counter"] = {"label": ctr.get("label", ""), "unit": ctr.get("unit", ""), "from": prev, "value": val}
            prev = val
        if b.get("shot"):
            data["widget"] = {"kind": "browser", "url": b["site"], "img": b["shot"]}
        elif b.get("pic"):
            data["widget"] = {"kind": "photo", "img": b["pic"], "credit": b.get("credit", "")}
        data["tint"], data["outfit"], data["look"] = tint, outfit, world
        data["gesture"] = gesture(i, len(st["beats"]), str(b["line"]), wd.get("kind"))
        data["swarm"] = False                                   # swarms are off (owner preference)
        if data["swarm"]:
            data["gesture"] = "wow"
        nxt = st["beats"][i + 1] if i + 1 < len(st["beats"]) else None      # the live bot's rhythm: short pause inside a stage, longer between stages
        pause = 0.28 if nxt is not None and int(nxt.get("stage") or 0) == int(b.get("stage") or 0) else 0.7
        scenes.append({"plate": "world", "pause": pause, "title": st["stages"][stage], "lines": [re.sub(r"\s+", " ", str(b["line"])).strip()], "data": data})
    return {"topic": st["title"], "scenes": scenes, "youtube": st.get("youtube", {}), "instagram_caption": st.get("instagram_caption", ""),
            "comment": st.get("comment"), "sources": st.get("sources", [])}


def capture_sites(st):
    try:
        return _capture_sites(st)
    except Exception as e:                       # live pages are a bonus - never fail the video over them
        print(f"  live pages skipped ({str(e)[:100]})")
        return 0


def _capture_sites(st):
    """Open each beat's real web page in headless Chrome and keep a screenshot for the 3D browser panel."""
    shots = BASE / "app" / "public" / "shots"
    shutil.rmtree(shots, ignore_errors=True)
    shots.mkdir(parents=True, exist_ok=True)
    todo = [(i, b) for i, b in enumerate(st["beats"]) if re.match(r"^https://[\w.-]+\.[a-z]{2,}(/\S*)?$", str(b.get("site") or ""))][:1]
    if not todo:
        return 0
    from playwright.sync_api import sync_playwright
    ok = 0
    with sync_playwright() as p:
        br = p.chromium.launch(channel=os.getenv("BROWSER_CHANNEL", "chrome"))
        ctx = br.new_context(viewport={"width": 860, "height": 1400}, device_scale_factor=1, accept_downloads=False,
                             user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36")
        for i, b in todo:
            page = ctx.new_page()
            try:
                r = page.goto(b["site"], wait_until="domcontentloaded", timeout=25000)
                if not r or r.status >= 400:
                    raise RuntimeError(f"HTTP {r.status if r else '?'}")
                page.wait_for_timeout(2500)
                f = shots / f"{i}.jpg"
                page.screenshot(path=str(f), type="jpeg", quality=88, full_page=False)
                b["shot"] = f"shots/{i}.jpg"
                ok += 1
                print(f"  🌐 live page for beat {i + 1}: {b['site']}")
            except Exception as e:
                print(f"  page skipped ({b['site']}): {str(e)[:80]}")
            finally:
                page.close()
        br.close()
    return ok


def tool(name):
    exe = shutil.which(name)
    if exe:
        return exe
    for p in (Path.home() / ".bun" / "bin" / f"{name}.exe",
              *Path(os.getenv("LOCALAPPDATA", "")).glob(f"Microsoft/WinGet/Packages/Oven-sh.Bun*/bun-windows-x64/{name}.exe")):
        if p.exists():
            return str(p)
    raise RuntimeError(f"{name} not found")


def make(topic, show=False):
    t0 = time.time()
    print(f"🎬 Pro story: {topic}")
    st = write_story(topic)
    print(f"  {len(st['beats'])} beats · stages: {' > '.join(st['stages'])} · example: {st.get('example')}")
    capture_sites(st)
    capture_photos(st)
    sc = to_script(st)
    sc["seed"] = random.randrange(1, 2 ** 31)
    sc["style"] = art_director.new_genome({}, len(sc["scenes"]))
    sc["style"].update(reflect=False, mascot={"on": False})
    out = BASE / "out" / f"{time.strftime('%Y%m%d-%H%M%S')}_pro"
    out.mkdir(parents=True, exist_ok=True)
    (out / "story.json").write_text(json.dumps(st, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "script.json").write_text(json.dumps(sc, indent=2, ensure_ascii=False), encoding="utf-8")
    audio_build.BETWEEN = 0.42                       # the live bot's rhythm: its average pause between sentences
    print("🔊 Narration")
    dur, voice = audio_build.narrate(sc)
    print(f"  {voice}, {dur:.1f}s")
    while dur > MAX_SECONDS and len(sc["scenes"]) > 11:          # hard cap: drop the weakest middle beat until it fits
        cut = max(range(2, len(sc["scenes"]) - 1), key=lambda i: (sc["scenes"][i]["data"].get("widget") or {}).get("kind") in ("checklist", "flow"))
        print(f"  {dur:.0f}s is over {MAX_SECONDS}s - dropping beat {cut + 1}")
        del sc["scenes"][cut]
        dur, voice = audio_build.narrate(sc)
    (out / "script.json").write_text(json.dumps(sc, indent=2, ensure_ascii=False), encoding="utf-8")
    env = dict(os.environ)
    env["PATH"] = os.pathsep.join([str(Path(audio_build.ffmpeg()).parent), str(Path(tool("bun")).parent), env.get("PATH", "")])
    subprocess.run([sys.executable, str(BASE / "analysis" / "audio_vo.py")], cwd=BASE, env=env, check=True)
    raw = BASE / "out" / "raw.mp4"
    print("🎞️ Rendering 1080x1920")
    render_parallel(env, raw, max(1, int(os.getenv("PRO_WORKERS") or 4)))
    mixed = audio_build.mix(sc)
    video = out / "video.mp4"
    subprocess.run([audio_build.ffmpeg(), "-v", "error", "-y", "-i", str(raw), "-i", str(mixed), "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest", str(video)], check=True)
    raw.unlink(missing_ok=True)
    print(f"✅ {video} ({dur:.0f}s) in {(time.time() - t0) / 60:.0f} min")
    if show and Path(VLC).exists():
        subprocess.Popen([VLC, str(video)])
    return video


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic", required=True)
    ap.add_argument("--show", action="store_true")
    a = ap.parse_args()
    make(a.topic, a.show)


def script_for(topic, facts=None, banned=()):
    """For the main bot: fact-checked story -> live pages + photos -> engine script (plates 'world')."""
    st = write_story(topic, facts, banned)
    print(f"  {len(st['beats'])} beats · stages: {' > '.join(st['stages'])} · example: {st.get('example')}")
    capture_sites(st)
    capture_photos(st)
    sc = to_script(st)
    sc["format"] = "world: " + " > ".join(st["stages"])
    sc["signatures"] = [g for g in (signature(b.get("widget")) for b in st["beats"]) if "@" in g]
    return sc


def fit_narration(sc):
    """Narrate at the live bot's rhythm and drop middle beats until the Short is at most MAX_SECONDS."""
    dur, voice = audio_build.narrate(sc)
    while dur > MAX_SECONDS and len(sc["scenes"]) > 11:
        cut = next((i for i in range(len(sc["scenes"]) - 2, 1, -1)
                    if not sc["scenes"][i]["data"].get("swarm") and not (sc["scenes"][i]["data"].get("widget") or {}).get("img")), len(sc["scenes"]) - 2)
        print(f"  {dur:.0f}s is over {MAX_SECONDS}s - dropping beat {cut + 1}")
        del sc["scenes"][cut]
        dur, voice = audio_build.narrate(sc)
    return dur, voice
