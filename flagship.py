"""
Flagship Shorts: one premium 45-60 s video per slot, built so that no two videos - and no two scenes - share a template.

  topic     today's biggest household-name tech story (pro.trend_topic), else the famous-topics list
  story     two fact-checked drafts in two different story formats; a judge keeps the stronger one
  look      a fresh art direction per video (style family, palette, fonts, captions, texture, transitions),
            never repeating the recent videos' family, fonts or background
  scenes    every beat is a HyperFrames scene written from scratch as HTML/CSS/GSAP for that sentence and that look,
            never reusing a layout already used in the video; scenes are linted and visually reviewed (Claude looks
            at a frame of each) and broken ones are rewritten
  finish    the bot's own narration (Andrew), music, mastering, QA gate, cover + carousel, A/B title, then posting

  python flagship.py --show                   # make one locally (nothing posted) and open it in VLC
  python flagship.py --post --at 12:00        # what the cloud runs: make it, wait for 12:00 ET, post
"""
import argparse
import base64
import html
import io
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
try:
    from dotenv import load_dotenv
    load_dotenv(BASE / ".env", override=True)
except ImportError:
    pass

import analytics  # noqa: E402
import main  # noqa: E402
import pro  # noqa: E402
import research  # noqa: E402
import writer  # noqa: E402

HF = BASE / "hf"
FPS = 30
W, H = 1080, 1920                       # set_canvas(True) switches to the 1920x1080 long-form canvas
FONTS = {p.stem: p for p in sorted((HF / "fonts").glob("*.ttf"))}
STORY_FORMATS = {
    "what-if": "WHAT IF IT STOPPED: open on what the viewer would lose if this system vanished for one minute, then show the "
               "hidden machinery that prevents it, part by part.",
    "myth": "MYTH vs TRUTH: open on the most common wrong belief about it, break it with the real mechanism, then the second "
            "myth, then the surprising truth.",
    "follow": "FOLLOW ONE THING: follow a single request / message / payment / frame from the moment the user taps until it "
              "arrives, stop by stop, with the clock running.",
    "countdown": "COUNTDOWN: the hidden steps that happen in the time it takes to blink, counted down to the one that "
                 "matters most.",
    "versus": "WHAT YOU SEE vs WHAT HAPPENS: alternate between the simple thing on screen and the enormous system behind it.",
    "inside": "INSIDE THE MACHINE: shrink the viewer down and fly through the system's real components as if they were places.",
}
FAMILIES = ["engineering blueprint (white/cyan line work on deep blue, measurement marks)",
            "isometric miniature city (tiny buildings and roads as the system's parts, soft shadows)",
            "editorial magazine (huge serif headlines, grid columns, paper tones, bold accent)",
            "product interface (the real app's own screens and UI components, rebuilt in HTML)",
            "macro hardware (chips, fibres, LEDs and circuit traces drawn in SVG, dramatic light)",
            "hand-drawn whiteboard (marker strokes that draw themselves, sticky notes, arrows)",
            "swiss poster (strict grid, giant numbers, two flat colours, heavy type)",
            "retro terminal (phosphor green or amber, ASCII diagrams, scanlines)",
            "paper cut-out (layered paper shapes with drop shadows, warm colours)",
            "data art (generative SVG lines, particles and charts built from the story's numbers)",
            "neon night city (dark, glowing signs and wires, reflections)",
            "infographic comic (panels, speech bubbles, bold outlines)"]

ART = """You are the art director of a premium {kind} ({w}x{h}).
Topic: "{topic}"
Story: {story}
Design a look that has NEVER been used on this channel. Recent looks (do NOT reuse their family, fonts or background
tone): {recent}
Pick ONE family from: {families}
Fonts available (use exact names): {fonts}
Return ONLY JSON: {{"name": 2-4 word name for this look, "family": the family you picked,
 "palette": {{"bg": hex, "ink": hex (main text, high contrast on bg), "accent": hex, "accent2": hex, "muted": hex}},
 "fonts": {{"display": font, "body": font, "mono": font}},
 "caption": {{"position": "top"|"center"|"bottom", "size": 52-74, "case": "upper"|"none",
             "highlight": "box"|"color"|"scale"|"underline", "panel": true|false}},
 "texture": "grid"|"grain"|"halftone"|"scanlines"|"none", "transition": "wipe"|"flash"|"cut"|"iris",
 "motion": one sentence describing the motion language (speed, easing, what moves),
 "rules": [5 short, concrete design rules every scene must follow so the video feels designed as one piece]}}"""

SCENE = """You design ONE scene of a premium {kind}, rendered by HyperFrames (HTML + CSS + GSAP).
LOOK (follow it exactly): {art}
SCRIPT AROUND THIS SCENE (for context): {script}
THIS IS SCENE {i} of {n}. It lasts {dur:.2f} s. The narrator says: "{line}"
Word timings (seconds from the scene start): {words}
Key idea / term: "{key}"   Visual idea from the writer: {idea}
Layouts ALREADY used in this video (do NOT repeat their composition, framing or main shape): {used}
Canvas: {w}x{h}. Keep everything inside x 60..{xmax} and y 40..{ymax}. The caption band y {cap0}..{cap1} is reserved for subtitles - put
NO important content there. Do not write the narration as body text (subtitles already show it); on-screen text is
labels, numbers and short headings only (max 6 words each, min 34px).
NUMBERS: only show a specific number, percentage or time if it appears in the SCRIPT above. Anything else must be
a shape without a value (bars, dots, a gauge) or be visibly marked as an example ("e.g.", "~"). Never invent statistics.
Make it unmistakably about THIS sentence: show the actual thing (a real UI, a chip, a packet, a server rack, a phone, a
map, numbers counting, a diagram that builds itself) drawn with HTML/CSS/inline SVG - no external images or fonts.
Motion: something new happens at least every ~1 s, timed to the word timings; an entrance in the first 0.4 s; never a
static frame. Use the LOOK's fonts via font-family names and its palette colours.
Technical rules (a violation breaks the render):
- "html": the scene's inner HTML only (no <script>, <style>, <img>, <video>, <link>); give elements short class names.
- "css": every selector MUST start with "#S " (it is replaced by this scene's id). Use position:absolute layouts.
  Never set a CSS transform on an element you also animate (set the start state in gsap.fromTo instead).
- "js": the BODY of function(tl, S, D, rand, A) - tl is this scene's GSAP timeline starting at 0, S is the scene
  selector (use S + " .name"), D the duration, rand() a seeded random 0..1 (never Math.random, Date or timers),
  A the palette ({{bg, ink, accent, accent2, muted}}). Only tl.to / tl.from / tl.fromTo / tl.set with explicit
  positions between 0 and D. No repeat:-1 (use a finite repeat that ends before D). No DOM queries outside S.
- Animate ONLY x, y, xPercent, yPercent, scale, scaleX, scaleY, rotation, opacity, autoAlpha, colours, strokeDashoffset
  and drawSVG-style dash values. NEVER tween left, top, right, bottom, width, height, margin, padding or font-size
  (they stutter in frame-by-frame capture) - position with CSS, move with x/y, grow with scale.
Return ONLY JSON: {{"layout": one line naming this scene's composition, "html": "...", "css": "...", "js": "..."}}
{feedback}"""

JUDGE = """Two drafts of a short vertical tech video about "{topic}". Which one will more viewers watch to the end AND send to a friend?
Judge the first sentence (does it stop the scroll?), clarity, surprise, and whether every line earns its place.
A: {a}
B: {b}
Return ONLY JSON: {{"pick": "A" or "B", "why": one line}}"""

REVIEW = """These are frames from the scenes of a tech video (one frame per scene, in order). Subtitles are added
later in the band y {cap0}..{cap1} (out of {h}), so ignore that band being empty.
For each frame, flag ONLY real problems: blank or nearly empty frame, text cut off or overflowing the canvas,
overlapping / unreadable text, broken layout (elements piled in a corner), or a frame that does not show anything
specific. Return ONLY JSON: {{"bad": [{{"scene": number from 1, "problem": "..."}}]}}"""


def set_canvas(land):
    global W, H
    W, H = (1920, 1080) if land else (1080, 1920)


def kind():
    return "8-10 minute landscape YouTube deep dive" if W > H else "short vertical tech explainer"


def log(msg):
    print(msg, flush=True)


def claude_vision(images, prompt):
    """images: list of PNG bytes. Uses the same Sonnet model as the story writer."""
    import anthropic
    from PIL import Image
    content = []
    for k, png in enumerate(images, 1):
        im = Image.open(io.BytesIO(png)).convert("RGB")
        im.thumbnail((960, 960))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=80)
        content += [{"type": "text", "text": f"Scene {k}:"},
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(buf.getvalue()).decode()}}]
    content.append({"type": "text", "text": prompt})
    r = anthropic.Anthropic(timeout=300.0, max_retries=2).messages.create(
        model=pro.STORY_MODEL, max_tokens=4000, messages=[{"role": "user", "content": content}])
    return json.loads(writer._json_text("".join(b.text for b in r.content if b.type == "text")))


# ------------------------------------------------------------------ topic + story
def pick_topic(state):
    deep = json.loads((BASE / "topics_deep.json").read_text(encoding="utf-8"))
    trend = pro.trend_topic(set(state["used_topics"]) | set(deep))
    if trend:
        log(f"🔥 Today's story: {trend['topic']}  ({trend['why']})")
        return trend["topic"], trend
    failed = state.get("failed_topics", {})
    return next(t for t in deep if t not in state["used_topics"] and failed.get(t, 0) < 2), None


def pick_length(state):
    """A/B: 25-40 s ("short") vs 45-60 s ("quick"), learned from what gets watched and pushed (40% exploration)."""
    if os.getenv("LENGTH_MODE") in ("short", "quick"):          # forced (local samples)
        return os.environ["LENGTH_MODE"]
    rnd = random.SystemRandom()
    modes = ["short", "quick"]
    return rnd.choice(modes) if rnd.random() < 0.4 else max(modes, key=lambda k: analytics.weight(state, "lmode", k) + rnd.random() * 0.01)


def best_story(topic, facts, state, mode="quick"):
    recent = [f.get("story_format") for f in state.get("flagship_styles", [])[-3:]]
    fmts = random.sample([k for k in STORY_FORMATS if k not in recent], 2)
    drafts = []
    for f in fmts:
        try:
            drafts.append((f, pro.write_story(topic, facts, (), mode, STORY_FORMATS[f])))
            log(f"  draft '{f}': {len(drafts[-1][1]['beats'])} beats")
        except Exception as e:
            log(f"  draft '{f}' failed ({str(e)[:100]})")
    if not drafts:
        raise RuntimeError("no draft passed the fact-check")
    if len(drafts) == 1:
        return drafts[0]
    lines = [" ".join(b["line"] for b in d[1]["beats"]) for d in drafts]
    j = json.loads(pro._story_llm(JUDGE.format(topic=topic, a=lines[0], b=lines[1])))
    k = 1 if str(j.get("pick", "A")).upper().startswith("B") else 0
    log(f"  judge picked '{drafts[k][0]}': {str(j.get('why', ''))[:120]}")
    return drafts[k]


# ------------------------------------------------------------------ art direction
def art_direction(topic, st, state):
    recent = state.get("flagship_styles", [])[-6:]
    rtxt = "; ".join(f"{r.get('family')} / {', '.join((r.get('fonts') or {}).values())} / bg {(r.get('palette') or {}).get('bg')}"
                     for r in recent) or "(none yet)"
    fams = [f for f in FAMILIES if not any(f.split(" (")[0] in str(r.get("family")) for r in recent[-4:])]
    for _ in range(3):
        a = json.loads(pro._story_llm(ART.format(kind=kind(), w=W, h=H, topic=topic, story=" ".join(b["line"] for b in st["beats"])[:1500], recent=rtxt,
                                                 families="; ".join(fams), fonts=", ".join(FONTS))))
        f, p = a.get("fonts") or {}, a.get("palette") or {}
        if all(f.get(k) in FONTS for k in ("display", "body", "mono")) and \
                all(re.fullmatch(r"#[0-9a-fA-F]{6}", str(p.get(k))) for k in ("bg", "ink", "accent", "accent2", "muted")):
            return a
        log("  art direction used an unknown font or colour - asking again")
    raise RuntimeError("no valid art direction")


def caption_band(art):
    pos = (art.get("caption") or {}).get("position", "bottom")
    if W > H:
        return {"top": (50, 230), "center": (430, 650), "bottom": (840, 1030)}.get(pos, (840, 1030))
    return {"top": (200, 520), "center": (800, 1120), "bottom": (1380, 1700)}.get(pos, (1380, 1700))


# ------------------------------------------------------------------ scenes
def scene_windows(lyrics, total):
    """[(start, end, line, words)] per scene from the narration (a scene runs until just before the next scene's first word)."""
    by = {}
    for ln in lyrics["lines"]:
        by.setdefault(ln["scene"], []).append(ln)
    keys = sorted(by)
    out = []
    for k, sid in enumerate(keys):
        s0 = 0.0 if k == 0 else by[sid][0]["start"] - 0.12
        s1 = (by[keys[k + 1]][0]["start"] - 0.12) if k + 1 < len(keys) else total
        words = [{"w": w["w"], "t": round(w["start"] - s0, 2)} for ln in by[sid] for w in ln["words"]]
        out.append((round(s0, 3), round(s1, 3), " ".join(ln["text"] for ln in by[sid]), words))
    return out


def write_scene(i, n, win, beat, art, script_txt, used, feedback=""):
    s0, s1, line, words = win
    cap0, cap1 = caption_band(art)
    idea = json.dumps(beat.get("widget") or {k: beat[k] for k in ("elements", "layout", "key") if k in beat}, ensure_ascii=False)[:700]
    for attempt in range(3):
        try:
            sc = json.loads(pro._story_llm(SCENE.format(
                kind=kind(), w=W, h=H, xmax=W - 60, ymax=H - 40, art=json.dumps(art, ensure_ascii=False), script=script_txt, i=i + 1, n=n, dur=s1 - s0, line=line,
                words=json.dumps(words, ensure_ascii=False), key=beat.get("key", ""), idea=idea, used="; ".join(used) or "(none yet)",
                cap0=cap0, cap1=cap1, feedback=feedback)))
            if all(isinstance(sc.get(k), str) and sc[k].strip() for k in ("html", "css", "js")) and "<script" not in sc["html"].lower():
                return sc
        except Exception as e:
            log(f"  scene {i + 1} attempt {attempt + 1} failed ({str(e)[:100]})")
    raise RuntimeError(f"scene {i + 1} could not be written")


def font_faces(art):
    return "\n".join(f'@font-face {{ font-family: "{name}"; src: url("fonts/{FONTS[name].name}"); }}'
                     for name in sorted(set((art.get("fonts") or {}).values())) if name in FONTS)


TEXTURE = {"grid": "background-image: linear-gradient(var(--m) 1px, transparent 1px), linear-gradient(90deg, var(--m) 1px, transparent 1px); background-size: 60px 60px; opacity: .18;",
           "halftone": "background-image: radial-gradient(var(--m) 1.6px, transparent 1.8px); background-size: 18px 18px; opacity: .22;",
           "scanlines": "background-image: repeating-linear-gradient(0deg, var(--m) 0 2px, transparent 2px 6px); opacity: .14;",
           "grain": "background-image: url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='240' height='240'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='2' seed='7'/></filter><rect width='100%' height='100%' filter='url(%23n)' opacity='.6'/></svg>\"); opacity: .12;",
           "none": "opacity: 0;"}


def build_page(art, wins, scenes, lyrics, total, seed):
    pal, cap, fonts = art["palette"], art.get("caption") or {}, art["fonts"]
    cap0, cap1 = caption_band(art)
    size = int(max(48, min(78, int(cap.get("size") or 62))) * (0.8 if W > H else 1))
    hl = cap.get("highlight", "color")
    css, body, js = [], [], []
    for i, ((s0, s1, _, _), sc) in enumerate(zip(wins, scenes)):
        sid = f"s{i}"
        css.append(sc["css"].replace("#S ", f"#{sid} ").replace("#S{", f"#{sid}{{"))
        body.append(f'<section id="{sid}" class="scene clip" data-start="{s0:.3f}" data-duration="{s1 - s0:.3f}" data-track-index="1">{sc["html"]}</section>')
        js.append(f'{{ const st = gsap.timeline(); try {{ (function(tl, S, D, rand, A) {{\n{sc["js"]}\n}})(st, "#{sid}", {s1 - s0:.3f}, rand, A); }} '
                  f'catch (e) {{ console.error("scene {i + 1}", e); }} tl.add(st, {s0:.3f}); }}')
    on = {"box": "{backgroundColor: A.accent, color: A.bg, duration: 0.06}", "scale": "{scale: 1.14, color: A.accent, duration: 0.08}",
          "underline": "{borderBottomColor: A.accent, color: A.accent, duration: 0.06}"}.get(hl, "{color: A.accent, duration: 0.06}")
    off = {"box": '{backgroundColor: "rgba(0,0,0,0)", color: A.ink, duration: 0.08}', "scale": "{scale: 1, color: A.ink, duration: 0.1}",
           "underline": '{borderBottomColor: "rgba(0,0,0,0)", color: A.ink, duration: 0.08}'}.get(hl, "{color: A.ink, duration: 0.08}")
    caps, cjs = [], []
    for k, ln in enumerate(lyrics["lines"]):
        caps.append(f'<div class="cl" id="c{k}">' + "".join(f'<span class="w" id="w{k}_{j}">{html.escape(w["w"])}</span> '
                                                           for j, w in enumerate(ln["words"])) + "</div>")
        cjs.append(f'tl.set("#c{k}", {{autoAlpha: 1}}, {ln["start"]:.3f}); tl.set("#c{k}", {{autoAlpha: 0}}, {ln["end"] + 0.25:.3f});')
        for j, w in enumerate(ln["words"]):
            cjs.append(f'tl.to("#w{k}_{j}", {on}, {w["start"]:.3f}); tl.to("#w{k}_{j}", {off}, {max(w["end"], w["start"] + 0.12):.3f});')
    tx = art.get("transition", "cut")
    for s0, *_ in wins[1:]:
        if tx == "wipe":
            cjs.append(f'tl.fromTo("#tx", {{xPercent: -101}}, {{xPercent: 101, duration: 0.34, ease: "power2.inOut"}}, {s0 - 0.17:.3f});')
        elif tx == "flash":
            cjs.append(f'tl.fromTo("#tx", {{opacity: 0}}, {{opacity: 0.85, duration: 0.07, yoyo: true, repeat: 1}}, {s0 - 0.07:.3f});')
        elif tx == "iris":
            cjs.append(f'tl.fromTo("#tx", {{opacity: 0.9, scale: 0}}, {{scale: 3, opacity: 0, duration: 0.4, ease: "expo.out"}}, {s0 - 0.05:.3f});')
    tx_css = {"wipe": "background: var(--a);", "flash": "background: var(--ink); opacity: 0;",
              "iris": "background: radial-gradient(circle, var(--a) 0 30%, transparent 31%); opacity: 0;"}.get(tx, "display: none;")
    shadow = f"background: {pal['bg']}cc; padding: 18px 26px; border-radius: 18px;" if cap.get("panel") else f"text-shadow: 0 3px 18px {pal['bg']};"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<script src="gsap.min.js"></script>
<style>
{font_faces(art)}
html, body {{ margin: 0; width: {W}px; height: {H}px; overflow: hidden; background: {pal["bg"]}; }}
#root {{ position: relative; width: 100%; height: 100%; overflow: hidden; background: {pal["bg"]}; color: {pal["ink"]};
        font-family: "{fonts["body"]}", sans-serif; --bg: {pal["bg"]}; --ink: {pal["ink"]}; --a: {pal["accent"]}; --a2: {pal["accent2"]}; --m: {pal["muted"]}; }}
#tex {{ position: absolute; inset: 0; pointer-events: none; {TEXTURE.get(art.get("texture"), TEXTURE["none"])} }}
.scene {{ position: absolute; inset: 0; overflow: hidden; }}
#caps {{ position: absolute; left: 60px; right: 60px; top: {cap0}px; height: {cap1 - cap0}px; }}
.cl {{ position: absolute; left: 0; right: 0; top: 50%; transform: translateY(-50%); text-align: center; visibility: hidden;
      font-family: "{fonts["display"]}", sans-serif; font-size: {size}px; line-height: 1.12; color: {pal["ink"]};
      {"text-transform: uppercase;" if cap.get("case") == "upper" else ""} {shadow} }}
.w {{ display: inline-block; padding: 0 6px; border-radius: 8px; border-bottom: 5px solid rgba(0,0,0,0); }}
#txw {{ position: absolute; inset: 0; pointer-events: none; }}
#tx {{ position: absolute; inset: 0; {tx_css} }}
{chr(10).join(css)}
</style>
</head>
<body>
<div id="root" data-composition-id="flagship" data-start="0" data-width="{W}" data-height="{H}" data-duration="{total:.3f}" data-fps="{FPS}">
  <div id="tex" class="clip" data-start="0" data-duration="{total:.3f}" data-track-index="0"></div>
  {chr(10).join(body)}
  <div id="caps" class="clip" data-start="0" data-duration="{total:.3f}" data-track-index="3">{"".join(caps)}</div>
  <div id="txw" class="clip" data-start="0" data-duration="{total:.3f}" data-track-index="4"><div id="tx"></div></div>
</div>
<script>
let _s = {seed % 2147483647 or 1};
function rand() {{ _s = (_s * 16807) % 2147483647; return (_s - 1) / 2147483646; }}
const A = {json.dumps(pal)};
const tl = gsap.timeline({{ paused: true }});
{"" if tx != "wipe" else 'tl.set("#tx", {xPercent: -101}, 0);'}
{chr(10).join(js)}
{chr(10).join(cjs)}
window.__timelines["flagship"] = tl;
</script>
</body>
</html>
"""


def npx(*args, timeout=900):
    env = {**os.environ, "HYPERFRAMES_NO_TELEMETRY": "1", "DO_NOT_TRACK": "1"}
    return subprocess.run([shutil.which("npx") or "npx", "--no-install", "hyperframes", *map(str, args)], env=env, cwd=str(HF),
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)


def lint_errors(work):
    r = npx("lint", work, "--json", timeout=300)
    try:
        data = json.loads(r.stdout[r.stdout.index("{"):])
    except ValueError:
        return [] if r.returncode == 0 else [(r.stdout + r.stderr)[-600:]]
    found = data.get("findings") or data.get("results") or []
    return [f"{f.get('code') or f.get('rule')}: {f.get('message')}" for f in found if str(f.get("severity", "")).lower() == "error"]


def snapshots(work, times):
    out = work / "snaps"
    shutil.rmtree(out, ignore_errors=True)
    r = npx("snapshot", work, "--at", ",".join(f"{t:.2f}" for t in times), "--no-end", "-o", out, timeout=600)
    pngs = sorted(out.rglob("*.png"), key=lambda p: [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", p.name)])
    if len(pngs) != len(times):
        raise RuntimeError(f"snapshot gave {len(pngs)} frames for {len(times)} scenes ({(r.stderr or r.stdout)[-200:]})")
    return [p.read_bytes() for p in pngs]


def make_page(art, wins, beats, lyrics, total, work, seed):
    def context(i):
        return " / ".join(w[2] for w in (wins if len(wins) <= 16 else wins[max(0, i - 3):i + 4]))
    scenes, used = [], []
    for i, (win, beat) in enumerate(zip(wins, beats)):
        sc = write_scene(i, len(wins), win, beat, art, context(i), used[-12:])
        scenes.append(sc)
        used.append(str(sc.get("layout", ""))[:80])
        log(f"  🎨 scene {i + 1}/{len(wins)}: {used[-1]}")
    for _ in range(2):                                           # lint, then a visual review of one frame per scene
        (work / "index.html").write_text(build_page(art, wins, scenes, lyrics, total, seed), encoding="utf-8")
        errs = lint_errors(work)
        bad = {}
        if errs:
            log(f"  lint: {len(errs)} error(s): {'; '.join(errs)[:300]}")
            bad = {i: "Lint errors: " + "; ".join(errs)[:600] for i in range(len(scenes)) if any(f"#s{i} " in e or f'"s{i}"' in e for e in errs)}
            props = {x.strip() for e in errs for m in re.findall(r"pixels: ([a-z, -]+)", e) for x in m.split(",") if x.strip()}
            if not bad and props:                                # selector not resolvable: blame the scenes that tween those props
                bad = {i: f"Lint error: you tweened {', '.join(sorted(props))} - animate with x/y/scale instead" for i, sc in enumerate(scenes)
                       if re.search(r"\b(" + "|".join(map(re.escape, props)) + r")\s*:", sc["js"])}
            if not bad:
                raise RuntimeError("composition does not pass lint: " + "; ".join(errs)[:300])
        else:
            cap0, cap1 = caption_band(art)
            shots, found = snapshots(work, [(w[0] + w[1]) / 2 for w in wins]), []
            for b0 in range(0, len(shots), 14):                  # the reviewer sees at most 14 frames at a time
                rv = claude_vision(shots[b0:b0 + 14], REVIEW.format(cap0=cap0, cap1=cap1, h=H))
                found += [{**b, "scene": int(b.get("scene", 0)) + b0} for b in rv.get("bad") or []]
            for b in found:
                k = int(b.get("scene", 0)) - 1
                if 0 <= k < len(scenes):
                    bad[k] = "A reviewer looked at a frame of your previous version and found: " + str(b.get("problem"))[:300]
            log(f"  👀 visual review: {len(bad)} scene(s) to redo" + (f" ({', '.join(str(k + 1) for k in bad)})" if bad else ""))
        if not bad:
            return scenes
        for k, why in bad.items():
            scenes[k] = write_scene(k, len(wins), wins[k], beats[k], art, context(k), (used[:k] + used[k + 1:])[-12:],
                                    f"PREVIOUS ATTEMPT WAS REJECTED - {why}\nPrevious attempt: {json.dumps(scenes[k], ensure_ascii=False)[:3000]}")
            used[k] = str(scenes[k].get("layout", ""))[:80]
    (work / "index.html").write_text(build_page(art, wins, scenes, lyrics, total, seed), encoding="utf-8")
    if lint_errors(work):
        raise RuntimeError("composition still fails lint after fixes")
    return scenes


# ------------------------------------------------------------------ the whole run
def design_and_render(art, script, lyrics, dur, out_dir):
    """Every scene designed from scratch for this look, reviewed, then rendered silent to out/raw.mp4."""
    wins = scene_windows(lyrics, dur)
    beats = [s.get("data") or {} for s in script["scenes"]][:len(wins)]
    work = BASE / "out" / "flagship_build"
    shutil.rmtree(work, ignore_errors=True)
    (work / "fonts").mkdir(parents=True)
    shutil.copy(HF / "node_modules/gsap/dist/gsap.min.js", work / "gsap.min.js")
    for name in set(art["fonts"].values()):
        shutil.copy(FONTS[name], work / "fonts" / FONTS[name].name)
    make_page(art, wins, beats, lyrics, dur, work, script["seed"])
    shutil.copy(work / "index.html", Path(out_dir) / "composition.html")
    log(f"🎞️ Rendering {len(wins)} scenes with HyperFrames ({W}x{H}, {dur:.0f}s)")
    raw = main.OUT / "raw.mp4"
    r = npx("render", work, "-o", raw, "--fps", FPS, "--quality", "looks", "--quiet", timeout=5 * 3600)
    if r.returncode != 0 or not raw.exists():
        raise RuntimeError(f"render failed: {(r.stderr or r.stdout)[-400:]}")
    return raw


def next_long_topic(long_st, script):
    done = set(long_st.get("used_topics", [])) | set(long_st.get("done_queue", [])) | {script["topic"], script.get("queue_topic")}
    queue = [t for t in long_st.get("next_topics", []) if t not in done]
    deep = [t for t in json.loads((BASE / "topics_deep.json").read_text(encoding="utf-8")) if t not in done]
    return (queue or deep or ["how the internet really works"])[0]


def make_long(state, topic=None):
    """The 8-10 minute landscape deep dive, built like the flagship Shorts: fresh look, every scene designed from scratch."""
    import audio_build
    import longform
    t0 = time.time()
    set_canvas(True)
    long_st = longform.load_long()
    script = longform.write(state, long_st, topic=topic)
    nxt = next_long_topic(long_st, script)
    last = script["scenes"][-1]
    script["scenes"].append({"plate": "compose", "title": "", "chapter": last.get("chapter"),
                             "lines": [f"Next deep dive: {nxt}. Subscribe so it lands in your feed."],
                             "data": {"chapter": dict((last.get("data") or {}).get("chapter") or {}), "key": "Subscribe"}})
    yt = script["youtube"]
    yt["description"] = yt.get("description", "") + f"\n\nNext deep dive: {nxt} - subscribe so you do not miss it."
    script.update(long=True, seed=random.randrange(1, 2 ** 31), format="flagship long")
    main.add_links(script, state)
    out_dir = main.OUT / f"{time.strftime('%Y%m%d-%H%M%S')}_long_{main.slugify(script['topic'])}"
    out_dir.mkdir(parents=True, exist_ok=True)
    log("🔊 Narration")
    dur, voice = audio_build.narrate(script)
    log(f"  {voice}, {dur:.0f}s, {len(script['scenes'])} scenes")
    lyrics = json.loads((BASE / "data" / "lyrics.json").read_text(encoding="utf-8"))
    recent = {"flagship_styles": state.get("flagship_styles", []) + long_st.get("styles", [])}
    art = art_direction(script["topic"], {"beats": [{"line": " ".join(s["lines"])} for s in script["scenes"]]}, recent)
    log(f"🎨 Look: {art.get('name')} - {art.get('family')} | fonts {', '.join(art['fonts'].values())} | bg {art['palette']['bg']}")
    p = art["palette"]
    script["style"] = {"name": art.get("name"), "palette": {"ink": p["bg"], "bone": p["ink"], "signal": p["accent"], "ash": p["muted"]}}
    raw = design_and_render(art, script, lyrics, dur, out_dir)
    video, meta = main.finish_video(script, {"out_dir": str(out_dir), "dur": dur, "voice": voice}, raw)
    log(f"✅ Long-form ready in {(time.time() - t0) / 60:.0f} min: {video}")
    return script, video, meta, {"family": art.get("family"), "fonts": art["fonts"], "palette": art["palette"], "name": art.get("name")}


def make(state, topic=None):
    t0 = time.time()
    trend = None
    if not topic:
        topic, trend = pick_topic(state)
    log(f"📌 Flagship topic: {topic}")
    facts = research.gather(topic, llm=writer.llm)
    log(f"📚 Research: {len(facts['sources'])} source(s)")
    mode = pick_length(state)
    log(f"  A/B length: {mode} ({pro.MODES[mode]['length']})")
    fmt, st = best_story(topic, facts, state, mode)
    script = pro.to_script(st)
    script["length_mode"], script["format"] = mode, f"flagship: {fmt}"
    main.pick_variants(script, state)
    main.add_sources(script, facts["sources"] + ((trend or {}).get("sources") or []))
    script.update(topic=script.get("topic") or topic, trend=trend, seed=random.randrange(1, 2 ** 31), angle=fmt, story_format=fmt)
    out_dir = main.OUT / f"{time.strftime('%Y%m%d-%H%M%S')}_flagship_{main.slugify(script['topic'])}"
    out_dir.mkdir(parents=True, exist_ok=True)
    log("🔊 Narration")
    dur, voice = pro.fit_narration(script)
    log(f"  {voice}, {dur:.1f}s")
    lyrics = json.loads((BASE / "data" / "lyrics.json").read_text(encoding="utf-8"))
    art = art_direction(script["topic"], st, state)
    log(f"🎨 Look: {art.get('name')} - {art.get('family')} | fonts {', '.join(art['fonts'].values())} | bg {art['palette']['bg']}")
    p = art["palette"]
    script["style"] = {"name": art.get("name"), "palette": {"ink": p["bg"], "bone": p["ink"], "signal": p["accent"], "ash": p["muted"]}}
    raw = design_and_render(art, script, lyrics, dur, out_dir)
    os.environ["HF_POST"] = "0"                      # the flagship is designed end to end - no generic chapter/share cards
    video, meta = main.finish_video(script, {"out_dir": str(out_dir), "dur": dur, "voice": voice}, raw)
    state.setdefault("flagship_styles", []).append({"family": art.get("family"), "fonts": art["fonts"], "palette": art["palette"],
                                                    "name": art.get("name"), "story_format": fmt})
    state["flagship_styles"] = state["flagship_styles"][-30:]
    log(f"✅ Flagship ready in {(time.time() - t0) / 60:.0f} min: {video}")
    return script, video, meta, topic


def slot_taken(slot):
    from zoneinfo import ZoneInfo
    hh, mm = map(int, slot.split(":"))
    target = datetime.now(ZoneInfo("America/Toronto")).replace(hour=hh, minute=mm, second=0, microsecond=0)
    last = next((p.get("time") for p in reversed(main.load_state().get("posts", [])) if p.get("time")), None)
    return bool(last and datetime.fromisoformat(last) > target - timedelta(hours=3))


def run():
    ap = argparse.ArgumentParser()
    ap.add_argument("--post", action="store_true")
    ap.add_argument("--at", help="post at this Eastern time (HH:MM)")
    ap.add_argument("--topic")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--long", action="store_true", help="the 8-10 min landscape deep dive")
    a = ap.parse_args()
    if a.long:
        return run_long(a)
    if a.post and datetime.now().date().isoformat() > main.RUN_UNTIL:
        log(f"Posting window ended on {main.RUN_UNTIL}.")
        return 0
    if a.post and a.at and slot_taken(a.at):
        log(f"⏭️ A video was already posted for the {a.at} ET slot - skipping")
        return 0
    state = main.load_state()
    if a.post:
        try:
            log(f"📈 Analytics: {analytics.collect(state)} post(s) refreshed")
            analytics.learn(state)
        except Exception as e:
            log(f"  analytics skipped ({e})")
    script, video, meta, topic = make(state, a.topic)
    if a.show and Path(main.VLC).exists():
        subprocess.Popen([main.VLC, str(video)])
    if not a.post:
        log("(local run - nothing posted)")
        return 0
    if a.at:
        subprocess.run([sys.executable, str(BASE / "wait_until.py"), a.at], check=False)
    return main.publish(script, video, meta, state, topic, False)


def run_long(a):
    import longform
    if a.post and datetime.now().date().isoformat() > main.RUN_UNTIL:
        log(f"Posting window ended on {main.RUN_UNTIL}.")
        return 0
    every = float(os.getenv("LONG_EVERY_DAYS") or 2)
    vids = longform.load_long()["videos"]
    if a.post and vids and not os.getenv("LONG_FORCE"):           # one long video every N days (the workflow checks daily)
        age = (datetime.now().astimezone() - datetime.fromisoformat(vids[-1]["time"])).total_seconds() / 86400
        if age < every - 0.5:
            log(f"Last long-form video was {age:.1f} days ago - the next one is due after {every:g} days")
            return 0
    state = main.load_state()
    script, video, meta, look = make_long(state, a.topic or os.getenv("LONG_TOPIC") or None)
    if a.show and Path(main.VLC).exists():
        subprocess.Popen([main.VLC, str(video)])
    if not a.post:
        log("(local run - nothing posted)")
        return 0
    if a.at:
        subprocess.run([sys.executable, str(BASE / "wait_until.py"), a.at], check=False)
    rc = main.publish(script, video, meta, state, None, True)
    ls = longform.load_long()                                     # publish saved the video; remember its look too
    ls.setdefault("styles", []).append(look)
    ls["styles"] = ls["styles"][-30:]
    longform.save_long(ls)
    return rc


if __name__ == "__main__":
    sys.exit(run())
