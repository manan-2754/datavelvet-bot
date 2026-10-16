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

KINDS = ["scene", "terminal", "code", "browser", "table", "chat", "phone", "request", "stack", "metric", "compare", "flow", "checklist", "summary"]
VLC = r"C:\Program Files\VideoLAN\VLC\vlc.exe"
MAX_SECONDS = 178                     # deep dives: 2-3 min, never over the 3:00 Shorts/Reels limit
MAX_WORDS = 390                       # ~140 words a minute (the live bot's pace) + pauses
# Length A/B: quick 45-60 s (completion rate) vs deep 2-3 min; analytics learns which one the algorithm pushes further.
MODES = {
    "deep": {"length": "2-3 minute", "stages": "5-7", "min_stages": 4, "count": "26-34 BEATS, 330-390 words total.",
             "beats": (22, 34), "words": MAX_WORDS, "seconds": MAX_SECONDS, "keep": 20, "ask": "26-34 beats",
             "shape": """1. HOOK (1-2 beats): beat 1 MUST be the single most surprising TRUE fact about the system (a number, a contrast or a
   myth it breaks) - never a slow intro. Beat 2 may say "Let's design <the system>."
2. USER VIEW (2-4 beats): the simplest thing a developer touches (a checkout call, a sign-in form, a deploy command) with a
   few lines of real code, and what they would normally have to build themselves around it.
3. REVEAL (1-2 beats): what is actually underneath (the real runtime / database / network / cluster).
4. LAYERS (12-18 beats): 3-6 REAL layers of the architecture, in order, 3-4 beats each. For every layer: what it is,
   the mechanism ("it does X, so Y happens"), ONE concrete demo with the running example travelling through it
   (a request, a row being written, a counter rising, an LED turning green), and ITS FAILURE CASE (what breaks / gets
   blocked / times out, and how the system handles it).
5. SCALE (3-5 beats): what happens at real scale - limits, the bottleneck hitting its ceiling, and the real fix.
6. REASSEMBLE (2-3 beats): the layers stack back into one system; replay the running example end to end.
7. END (1 beat): the one-line payoff that loops back into beat 1 (see LOOP)."""},
    "short": {"length": "25-40 second", "stages": "2-3", "min_stages": 2, "count": "6-8 BEATS, 70-95 words total.",
              "beats": (6, 8), "words": 100, "seconds": 40, "keep": 5, "ask": "6-8 beats",
              "shape": """1. HOOK (1 beat): the single most surprising TRUE fact about it - a claim a viewer would forward to a friend.
2. MECHANISM (4-6 beats): the ONE real mechanism that explains the hook, shown with the running example. Nothing else -
   cut every side point; a 30-second Short watched to the end beats a longer one watched halfway.
3. PAYOFF (1 beat): the aha that answers the hook, ending on the loop line (see LOOP)."""},
    "quick": {"length": "45-60 second", "stages": "3-4", "min_stages": 3, "count": "9-12 BEATS, 100-135 words total.",
              "beats": (8, 12), "words": 140, "seconds": 60, "keep": 7, "ask": "9-12 beats",
              "shape": """1. HOOK (1 beat): the single most surprising TRUE fact about the system (a number, a contrast or a myth it
   breaks) - never a slow intro.
2. REVEAL (1 beat): what is actually underneath.
3. LAYERS (5-8 beats): the 2-3 REAL layers that explain the hook, in order: the mechanism ("it does X, so Y happens") with
   the running example travelling through it; ONE failure case in total.
4. PAYOFF (1-2 beats): the aha that answers the hook, ending on the loop line (see LOOP). Every second must earn its place."""},
}
PROMPT = """You write a {length} vertical deep-dive for developers on "DataVelvet": "How does {topic} really work under
the hood?" Explain the REAL mechanism, like a senior engineer whiteboarding it - not a beginner overview.
{facts}
DO NOT use a fixed template or a fixed scene order. Derive the sequence from the real architecture of the topic: start from
what the developer/user touches, peel back each real layer, then rebuild the whole system. Keep this SHAPE (rename freely):
{shape}
Rules:
- ONE running example through everything (e.g. "Maya pays $24 for sneakers", "a push to main at 9:41").
- {stages} STAGES = the real layers' short names (max 12 chars), in order. Every beat belongs to one stage.
- {count} Each beat = ONE spoken sentence of 9-15 words: short, direct, one idea, the mechanism.
  Use the same key nouns every time they reappear so viewers can track them.
- Use real terms (idempotency key, WAL, consensus, edge cache, TLS handshake...) and explain them in plain words.
- Numbers must come from the reference facts or official docs; otherwise describe without a number. Never invent metrics.
- Each beat: "chapter": "hook"|"user"|"reveal"|"layer"|"scale"|"reassemble"|"end"; "theme": "light" for user-facing views
  (user, end) and "dark" for internals (reveal, layer, scale).
- Each beat gets ITS OWN VISUAL, designed from scratch for exactly what that sentence says. Mostly use
  "scene" (a free composition you design): {{"kind": "scene", "elements": 2-6 {{"id", "type", "x": 0-100, "y": 0-100,
  "size": "S"|"M"|"L", "label": max 18 chars, "sub": max 22 chars, "color": "emerald"|"blue"|"amber"|"cyan"|"violet"|"rose"|"white",
  "count", "items": [...], "value", "translate", "enter": "pop"|"drop"|"slide"|"zoom"|"unfold", "motion": "float"|"pulse"|"spin"|"none",
  "at": 0-0.8 (when it pops in, as a fraction of the beat), "exit": "dot" to collapse into a dot when the beat ends}}, "links": 0-5 {{"from": id, "to": id, "label": max 14 chars, "color"}}}}.
  Element types: cylinder (database, "count" = rings), stack (isometric layers, "items" = layer names bottom first),
  tower (server/console), orbit (a core with "count" avatars/icons orbiting it in 3D, "items" = their names), node (service/UI card),
  code ("items" = 2-5 code lines typed live, OR "translate": {{"from_lang", "to_lang", "from": [lines], "to": [lines]}} morphing
  one language into another), metric ("value": e.g. "4.2 ms", label = what it is), avatars ("items" = first names), globe ("count" = glowing arcs between regions),
  gauge ("value": 0-1), slots ("value": 0-1 how full; past 80% the cells turn red = a limit being hit),
  vm (an isolated microVM box, "items" = its own kernel/filesystem/network rows), queue ("items" = what is waiting), bars ("items" = numbers), lock, cloud, file, user, chip, phone, badge.
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
{banned}- "key": 1-2 words copied EXACTLY from the beat's sentence to highlight (the key term only).
- Failure cases: use color "rose", a badge like "BLOCKED"/"TIMEOUT"/"402 DECLINED", table "marks": false, or a slots grid filling red.
- "object": a 3D object for the beat's stage, one of {objects}.
- A running "counter" that grows along the journey (e.g. elapsed ms, km travelled, bytes) - give its value per beat.
- LOOP: the final beat's sentence must end on words that lead straight back into beat 1's sentence, so when the Short
  replays the two lines read as one continuous thought (e.g. last: "...and that is why" -> first: "ChatGPT never knows its
  answer."). No "follow for more", no goodbye - the loop is the ending.
Accurate facts only; never invent statistics; no emojis; no "in this video".
Return ONLY JSON:
{{"title": max 60 chars, "example": the running example (max 34 chars), "stages": [...], "counter": {{"label": e.g. "T+",
 "unit": e.g. "ms"}}, "beats": [{{"stage": index, "chapter": "...", "theme": "light"|"dark", "line": "...", "key": "...",
 "object": "...", "counter": number,
 "widget": {{"kind": "...", ...}}}}], "hook_text": the first-frame headline, max 6 words, punchy and true (e.g. "ChatGPT never knows its answer"),
 "titles": {{"curiosity": max 70 chars ending " #shorts", brand first + curiosity gap, "direct": max 70 chars ending " #shorts",
 a plain "How <brand> <does X> under the hood" title}},
 "youtube": {{"title": the curiosity title, "description": 2 sentences + 5
 hashtags, "tags": [6-8]}}, "share_line": max 48 chars, a specific "Send this to the dev who..." / "Send this to a friend who..." ask that fits this topic,
 "instagram_caption": line 1 = the share_line, then 2 lines + 6 hashtags, "comment": one either/or question that is easy to answer}}
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


def _review(sc):
    """Fact-check with the same strong model that wrote it (consistent on deep technical detail)."""
    rows = [f"{i + 1}. [{s['plate']}] {s['title']}: {' '.join(s['lines'])}  (on screen: {json.dumps(s['data'], ensure_ascii=False)[:400]})"
            for i, s in enumerate(sc["scenes"])]
    data = json.loads(_story_llm(DEEP_REVIEW.format(topic=sc["topic"], script="\n".join(rows))))
    crit = [str(x) for x in data.get("critical_errors") or [] if not re.search(r"\bno error\b|\bnot a factual\b", str(x), re.I)]
    return {"score": int(data.get("score", 0)), "critical": crit, "minor": [str(x) for x in data.get("minor_issues") or []]}


DEEP_REVIEW = """You are a staff engineer fact-checking a short developer deep-dive about "{topic}" before it is published.
Each numbered beat is one spoken sentence plus what is on screen.
{script}
Classify problems carefully:
- critical_errors: ONLY statements that are factually FALSE, or that would give a developer a WRONG mental model of how the
  system works (wrong order of steps, wrong component doing the work, invented numbers, wrong API/protocol behaviour).
- minor_issues: simplifications that are directionally correct, missing caveats or edge cases, defaults that vary by
  configuration, wording nitpicks. These are acceptable in a short video and must NOT be listed as critical.
Score 0-10 for accuracy + depth + clarity for developers.
Return ONLY JSON: {{"score": n, "critical_errors": ["beat N: what is false and what is true", ...], "minor_issues": [...]}}"""


FIX = """Below is a video story as JSON; its beats are numbered from 1. A fact-checker found these errors:
- {errors}
Fix ONLY the beats involved (sentence and/or on-screen widget). Keep every other beat exactly as it is, keep the same
running example, keep each sentence 9-15 words. Prefer removing or softening a claim to guessing.
Return ONLY JSON: {{"beats": {{"<beat number>": <the full corrected beat object>}}}}
STORY:
{story}"""


def _fix_lines(st, beats, errors):
    """Targeted repair: rewrite only the flagged beats, so fixing one error does not introduce new ones."""
    out = json.loads(_story_llm(FIX.format(errors="\n- ".join(errors), story=json.dumps({**st, "beats": beats}, ensure_ascii=False)[:14000])))
    fixed = dict(enumerate(beats, 1))
    for k, b in (out.get("beats") or {}).items():
        if str(k).isdigit() and int(k) in fixed and isinstance(b, dict) and len(str(b.get("line", "")).split()) >= 4:
            fixed[int(k)] = {**fixed[int(k)], **b}
    print(f"  targeted fix of beat(s) {', '.join(str(k) for k in (out.get('beats') or {}))}")
    return [fixed[i] for i in sorted(fixed)]


def write_story(topic, facts=None, banned=(), mode="deep", angle=""):
    m = MODES[mode]
    facts = facts or research.gather(topic, llm=writer.llm)
    ftxt = (f"REFERENCE FACTS (from {', '.join(facts['sources'][:3])}) - use their numbers:\n{facts['facts'][:3500]}") if facts.get("facts") else ""
    fb = ""
    for attempt in range(6):
        ban = ("- These scene layouts were already used in earlier videos - do NOT reproduce any of them:\n  " + "\n  ".join(list(banned)[-60:])) if banned else ""
        ban = (f"- STORY FORMAT for this video (overrides the SHAPE above where they differ): {angle}\n" if angle else "") + ban
        st = json.loads(_story_llm(PROMPT.format(topic=topic, facts=ftxt, objects=", ".join(writer.OBJECTS), feedback=fb, banned=ban,
                                                 length=m["length"], shape=m["shape"], stages=m["stages"], count=m["count"])))
        beats = [b for b in (st.get("beats") or []) if isinstance(b, dict) and len(str(b.get("line", "")).split()) >= 4]
        stages = [str(s)[:12] for s in (st.get("stages") or [])][:7]
        words = sum(len(str(b['line']).split()) for b in beats)
        if len(beats) < m["beats"][0] or len(stages) < m["min_stages"] or words > m["words"]:
            fb = f"\nThe previous draft had {len(beats)} beats, {words} words and {len(stages)} stages - give {m['ask']}, at most {m['words']} words in total, and {m['stages']} stages." + ("\nPREVIOUS DRAFT (shorten it, keep the best beats):\n" + json.dumps(st, ensure_ascii=False)[:9000] if words > m["words"] else "")
            continue
        sigs = [signature(b.get("widget")) for b in beats]
        seen, clash = set(banned), []
        for i, g in enumerate(sigs):
            if "@" in g and g in seen:
                clash.append(i + 1)
            seen.add(g)
        n_scene = sum(1 for b in beats if (b.get("widget") or {}).get("kind") == "scene")
        if (clash or n_scene < len(beats) * 0.6) and attempt < 2:
            fb = (f"\nRedesign: beats {clash} reuse a layout that already exists" if clash else "\nRedesign:") + (f"; only {n_scene} of {len(beats)} beats are designed scenes - make at least 70% of beats 'scene' compositions" if n_scene < len(beats) * 0.6 else "") + ". Keep the same lines.\nPREVIOUS DRAFT:\n" + json.dumps(st, ensure_ascii=False)[:9000]
            print(f"  redesign asked (clashes {clash}, {n_scene}/{len(beats)} scenes)")
            continue
        sc = {"topic": topic, "scenes": [{"plate": "story", "title": stages[min(len(stages) - 1, int(b.get("stage") or 0))],
                                          "lines": [b["line"]], "data": {"widget": b.get("widget")}} for b in beats]}
        rv = _review(sc)
        print(f"  fact-check: {rv['score']}/10, {len(rv['critical'])} real error(s)")
        for c in rv["critical"]:
            print(f"    - {c[:160]}")
        fixes = 0
        while rv["critical"] and len(rv["critical"]) <= 4 and fixes < 3:      # close: repair only the flagged beats
            beats, fixes = _fix_lines(st, beats, rv["critical"]), fixes + 1
            sc = {"topic": topic, "scenes": [{"plate": "story", "title": stages[min(len(stages) - 1, int(b.get("stage") or 0))],
                                              "lines": [b["line"]], "data": {"widget": b.get("widget")}} for b in beats]}
            rv = _review(sc)
            print(f"  fact-check after fix: {rv['score']}/10, {len(rv['critical'])} real error(s)")
            for c in rv["critical"]:
                print(f"    - {c[:160]}")
        if rv["critical"] and len(beats) > m["beats"][0] + 2:                        # last resort: drop the beats that still carry a doubtful claim
            bad = {int(n) for c in rv["critical"] for n in re.findall(r"beats?\s*(\d+)", c, re.I)}
            bad = {n for n in bad if 2 < n < len(beats)}               # never the hook or the ending
            if bad and len(beats) - len(bad) >= m["beats"][0]:
                beats = [b for i, b in enumerate(beats, 1) if i not in bad]
                sc = {"topic": topic, "scenes": [{"plate": "story", "title": stages[min(len(stages) - 1, int(b.get("stage") or 0))],
                                                  "lines": [b["line"]], "data": {"widget": b.get("widget")}} for b in beats]}
                rv = _review(sc)
                print(f"  dropped beat(s) {sorted(bad)} -> fact-check: {rv['score']}/10, {len(rv['critical'])} real error(s)")
        if not rv["critical"] and rv["score"] >= 6:
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
             "ambient": look.choice(["rings", "particles", "beams"]), "floor": look.choice(["dots", "lines", "cross"]),
             "reveal": look.choice(["scan", "draw", "assemble", "glitch"]), "holoFloor": look.choice(["polar", "hex", "grid", "dots"])}
    modes, last = ["fly", "orbit", "crane", "dolly", "low", "top", "dutch", "spiral", "whip", "push"], None
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
                "light": str(b.get("theme", "")).lower() == "light"}
        if val is not None:
            data["counter"] = {"label": ctr.get("label", ""), "unit": ctr.get("unit", ""), "from": prev, "value": val}
            prev = val
        if b.get("shot"):
            data["widget"] = {"kind": "browser", "url": b["site"], "img": b["shot"]}
        elif b.get("pic"):
            data["widget"] = {"kind": "photo", "img": b["pic"], "credit": b.get("credit", "")}
        data["tint"], data["outfit"], data["look"] = tint, outfit, world
        last = data["cam"] = look.choice(["whip", "push", "dolly"] if i == 0 else [m for m in modes if m != last])   # beat 1 moves fast from frame 0
        data["gesture"] = gesture(i, len(st["beats"]), str(b["line"]), wd.get("kind"))
        data["swarm"] = False                                   # swarms are off (owner preference)
        if data["swarm"]:
            data["gesture"] = "wow"
        nxt = st["beats"][i + 1] if i + 1 < len(st["beats"]) else None      # the live bot's rhythm: short pause inside a stage, longer between stages
        pause = 0.28 if nxt is not None and int(nxt.get("stage") or 0) == int(b.get("stage") or 0) else 0.7
        scenes.append({"plate": "world", "pause": pause, "title": st["stages"][stage], "lines": [re.sub(r"\s+", " ", str(b["line"])).strip()], "data": data})
    if scenes and st.get("hook_text"):                          # big headline on the first frame
        scenes[0]["data"]["hook_text"] = str(st["hook_text"])[:48]
    return {"title_variants": {k: str(v)[:100] for k, v in (st.get("titles") or {}).items() if k in ("curiosity", "direct") and v},
            "topic": st["title"], "scenes": scenes, "youtube": st.get("youtube", {}), "instagram_caption": st.get("instagram_caption", ""),
            "comment": st.get("comment"), "sources": st.get("sources", []), "share_line": str(st.get("share_line") or "")[:60]}


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
    while dur > MAX_SECONDS and len(sc["scenes"]) > 20:          # hard cap: drop the weakest middle beat until it fits
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


def script_for(topic, facts=None, banned=(), mode="deep"):
    """For the main bot: fact-checked story -> live pages + photos -> engine script (plates 'world')."""
    st = write_story(topic, facts, banned, mode)
    print(f"  {len(st['beats'])} beats · stages: {' > '.join(st['stages'])} · example: {st.get('example')}")
    capture_sites(st)
    capture_photos(st)
    sc = to_script(st)
    sc["format"] = "world: " + " > ".join(st["stages"])
    sc["length_mode"] = mode
    sc["signatures"] = [g for g in (signature(b.get("widget")) for b in st["beats"]) if "@" in g]
    return sc


def fit_narration(sc):
    """Narrate at the live bot's rhythm and drop middle beats until the Short is at most MAX_SECONDS."""
    m = MODES[sc.get("length_mode") or "deep"]
    dur, voice = audio_build.narrate(sc)
    while dur > m["seconds"] and len(sc["scenes"]) > m["keep"]:
        cut = next((i for i in range(len(sc["scenes"]) - 2, 1, -1)
                    if not sc["scenes"][i]["data"].get("swarm") and not (sc["scenes"][i]["data"].get("widget") or {}).get("img")), len(sc["scenes"]) - 2)
        print(f"  {dur:.0f}s is over {m['seconds']}s - dropping beat {cut + 1}")
        del sc["scenes"][cut]
        dur, voice = audio_build.narrate(sc)
    return dur, voice


TREND = """Here are today's top tech stories:
{items}
Pick ONE that MANY people know about AND would forward to a friend ("did you know your phone...", a surprising
hidden mechanism, a big outage everyone felt) - prefer big, famous brands, products, launches or outages (OpenAI, Apple, Google,
AWS, Meta, Microsoft, Netflix, Tesla, a major outage) over niche hobby projects - and turn it into a deep-dive topic about how the real system behind it
works under the hood (e.g. an outage -> "How AWS us-east-1 really works", a model launch -> "How <model> generates text").
Only real, current events from the list; the topic must be explainable from public engineering docs. Not any of: {used}
The topic MUST be about a household-name product or company that a non-programmer already uses or has heard of (ChatGPT, iPhone,
WhatsApp, Netflix, Google, AWS, Tesla...). Programming languages, libraries, protocols and research papers do NOT count. If no story
in the list is about such a brand, return {{"topic": "", "brand": null}} - do not settle for a niche story.
Return ONLY JSON: {{"topic": max 70 chars, a "how X works under the hood" subject (no "How does"), "brand": the household-name brand
it is about (it must appear in the topic), "why": one line, "source_index": n}}"""


def trend_topic(used):
    """Today's tech news -> a deep-dive topic (one slot a day)."""
    import trends
    items = sorted(trends.gather() or [], key=lambda x: -x.get("score", 0))[:40]
    if not items:
        return None
    try:
        res = json.loads(_story_llm(TREND.format(items="\n".join(f"{i}. [{x['src']}] {x['title']}" for i, x in enumerate(items)),
                                                 used=", ".join(list(used)[-80:]))))
        topic = str(res.get("topic", "")).strip()
        brand = str(res.get("brand") or "").strip()
        if not topic or topic in used:
            return None
        if not brand or brand.lower() not in topic.lower():          # no famous brand -> the famous-topics list takes this slot
            print(f"  trend skipped (no household-name brand in: {topic[:60]})")
            return None
        i = res.get("source_index")
        src = items[i]["url"] if isinstance(i, int) and 0 <= i < len(items) else None
        return {"topic": topic[:80], "why": str(res.get("why", ""))[:160], "sources": [src] if src else []}
    except Exception as e:
        print(f"  tech trend pick failed ({e})")
        return None
