"""
Carousel lane: one standalone, save-worthy Instagram carousel a day, separate from the Reels - its own topics and
formats (cheat sheet, X vs Y, myth vs fact, step-by-step, N things, mini glossary), with a 3D hero image rendered by
the engine on every slide (the visual edge over flat template carousels). Shares the channel's token, style system
and never-repeat memory; its own history lives in carousel_state.json.

  python carousel_lane.py --format versus --topic "SSD vs hard drive"     # make one locally (nothing posted)
  python carousel_lane.py --post                                           # what the cloud runs once a day
"""
import argparse
import json
import os
import random
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
try:
    from dotenv import load_dotenv
    load_dotenv(BASE / ".env", override=True)
except ImportError:
    pass

from PIL import Image, ImageDraw  # noqa: E402

import art_director  # noqa: E402
import composer  # noqa: E402
import covers  # noqa: E402
import deck  # noqa: E402
import research  # noqa: E402
import writer  # noqa: E402
from main import env_with_tools, load_state, tool  # noqa: E402

STATE = BASE / "carousel_state.json"
W, H = 1080, 1350
FORMATS = {
    "cheatsheet": ("CHEAT SHEET", "a cheat sheet: 5 compact, genuinely useful facts or rules someone would screenshot"),
    "versus": ("VS", "an X vs Y comparison: 5 rows comparing the two on concrete criteria with real numbers where known"),
    "mythfact": ("MYTH vs FACT", "5 common myths, each busted with the real fact"),
    "steps": ("STEP BY STEP", "how it works in 5 clear steps, in order"),
    "things": ("SAVE THIS", "5 practical things a normal user should know or do (settings, habits, checks)"),
    "glossary": ("GLOSSARY", "5 terms people hear but don't understand, each explained in one plain sentence"),
}
IDEAS = {
    "cheatsheet": ["Wi-Fi speed cheat sheet", "Phone battery health cheat sheet", "Password security cheat sheet",
                   "Internet speed units explained (Mbps vs MB/s)", "Keyboard shortcuts that save hours"],
    "versus": ["SSD vs hard drive", "Wi-Fi 6 vs Wi-Fi 7", "4G vs 5G", "RAM vs storage", "VPN vs incognito mode", "USB-C vs Lightning"],
    "mythfact": ["Phone battery myths", "Wi-Fi myths", "Computer virus myths", "Internet privacy myths", "Charging myths"],
    "steps": ["What happens when you send a text message", "How a website loads in your browser", "How two-factor login works",
              "How your phone finds a cell tower", "How a QR code works"],
    "things": ["Things to do when your phone feels slow", "Signs your password was leaked", "Ways to make Wi-Fi faster at home",
               "Settings that protect your privacy online", "Habits that make your laptop battery last longer"],
    "glossary": ["Internet terms everyone uses but nobody explains", "AI words explained", "Cybersecurity terms explained",
                 "Phone spec sheet terms explained", "Cloud computing terms explained"],
}
PLAIN = ('Write for a normal phone and laptop user, not an engineer: plain every'
         'day words, short sentences. Avoid jargon and acronyms (protocol names, standards, part numbers); if one is unavoidable, explain it in a few words.')
DEV_FORMATS = ["cheatsheet", "steps", "glossary", "mythfact"]       # developer lane (no consumer-style "versus" / "things")
AUDIENCE_DEV = ("Write for developers and curious tech people: use the real terms (e.g. TLS handshake, idempotency key) and explain each in a few "
                "words, with concrete numbers and mechanisms. Specific beats generic - a slide someone would screenshot for an interview.")
WRITE = """You write a premium Instagram carousel for "DataVelvet", a 3D tech-explainer brand.
Topic: "{topic}"
Format: {fmt_desc}
{facts}
Return ONLY JSON:
{{"title": cover headline, max 48 chars: a HARD HOOK headline: a surprising number, a myth it breaks, or a bold promise that is true (e.g. "Chrome runs 1 process per tab", "5 things your browser does before the page loads"), "icon": one of {icons},
  "subtitle": max 70 chars,
  "a": first item name (versus only, else ""), "b": second item name (versus only, else ""),
  "slides": [5 objects: {{"heading": max 34 chars, "body": max 140 chars, plain and specific,
     "a": versus value for a (max 38 chars, versus only), "b": versus value for b (versus only),
     "verdict": "MYTH" or "FACT" (mythfact only: the heading is the claim, body the truth),
     "score_a", "score_b": 1-5 how well a and b do on this point for a typical user (versus only),
     "icon": one of {icons}}}],
  "takeaway": one-line summary, max 90 chars,
  "caption": line 1 = a hook, line 2 = the specific reason to save it (e.g. "Save this before your next system-design interview."), then 6 relevant hashtags}}
{audience}
Rules: accurate, specific facts only (use the reference facts' numbers; never invent statistics); no emojis inside
slides; pick the icon that best matches each slide."""
TYPES = ["box", "sphere", "cylinder", "cone", "prism", "torus", "ring", "panel", "bars", "donut", "gauge", "counter", "text", "code",
         "link", "stream", "network", "orbit", "object"]
LAYOUTS = ["row", "radial", "grid", "stack", "pyramid", "diagonal", "cluster", "ring"]


def gen(prompt, label, dev):
    """Developer carousels are written by the same strong model as the deep-dive Shorts."""
    if dev:
        import pro
        return pro._story_llm(prompt)
    return writer.llm(prompt, label=label)


def check(sc, dev):
    """Fact-check gate: (ok, report). Developer content is judged on real errors only (not consumer-style nitpicks)."""
    if dev:
        import pro
        rv = pro._review(sc)
        ok = not rv["critical"] and rv["score"] >= 6
    else:
        rv = writer.review(sc)
        ok = not rv["critical"] and rv["score"] >= 7
    print(f"  fact-check: {rv['score']}/10, {len(rv['critical'])} real error(s)")
    for c in rv["critical"]:
        print(f"    - {c[:150]}")
    return ok, rv


def load_cs():
    st = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    st.setdefault("posts", [])
    return st


def write_content(topic, fmt, dev=False):
    facts = research.gather(topic, llm=writer.llm)
    ftxt = (f"REFERENCE FACTS (from {', '.join(facts['sources'][:3])}):\n{facts['facts'][:3000]}") if facts.get("facts") else ""
    err = ""
    for attempt in range(3):
        c = json.loads(gen(WRITE.format(topic=topic, fmt_desc=FORMATS[fmt][1], facts=ftxt, icons=", ".join(deck.ICONS), audience=AUDIENCE_DEV if dev else PLAIN) + err,
                           "carousel", dev))
        slides = [s for s in (c.get("slides") or []) if isinstance(s, dict) and s.get("heading")][:6]
        if len(slides) < 4:
            err = f"\nYour previous answer had only {len(slides)} usable slides - give 5."
            continue
        c["slides"] = slides
        sc = {"topic": topic, "scenes": [{"plate": "compose", "title": s["heading"], "lines": [s.get("body", ""),
              *([f'{c.get("a")}: {s.get("a")}; {c.get("b")}: {s.get("b")}'] if fmt == "versus" else [])], "data": {}} for s in slides]}
        ok, rv = check(sc, dev)                     # the same fact-check gate the videos use
        if ok:
            c["sources"] = facts["sources"]
            return c
        err = "\nA fact-checker rejected the previous version. Fix every point:\n- " + "\n- ".join(rv["critical"] + rv["minor"])
    raise RuntimeError("no carousel passed the fact-check")


def fake_timeline(content, genome, labels=True):
    """Engine input for stills only: one composed 3D scene per slide (no narration)."""
    scenes, lines, t = [], [], 0.4
    for i, s in enumerate([{"heading": content["title"], "visual": content.get("visual") or content["slides"][0].get("visual")}] + content["slides"]):
        v = s.get("visual") or {}
        els = [e for e in (v.get("elements") or []) if isinstance(e, dict)][:3] or [{"type": "sphere", "label": "IDEA"}, {"type": "ring", "label": ""}]
        words, out = [], []
        for k, e in enumerate(els):
            lab = re.sub(r"[^A-Za-z0-9 ]", "", str(e.get("label") or f"item{k}")).strip() or f"item{k}"
            cue = lab.split()[0]
            words.append({"w": cue, "start": round(t + 0.3 + k * 0.5, 3), "end": round(t + 0.6 + k * 0.5, 3)})
            typ = e.get("type") if e.get("type") in TYPES else "sphere"
            typ = "panel" if typ in ("text", "counter") else typ          # big 3D words compete with the slide heading
            out.append({"type": typ, "label": lab[:18].upper(), "cue": cue, **({"object": e["object"]} if e.get("object") else {}),
                        **({} if labels else {"label": ""}), "anim": "grow", "idle": "float", "tone": ["holo", "alt", "accent"][k % 3], "size": float(e.get("size") or 1.25)})
        if len({e["type"] for e in out}) < 2:
            out[-1]["type"] = "ring" if out[0]["type"] != "ring" else "sphere"
        end = t + 0.6 + len(out) * 0.5 + 1.2
        lines.append({"text": " ".join(w["w"] for w in words), "start": words[0]["start"], "end": end - 0.4, "scene": i, "words": words})
        scenes.append({"plate": "compose", "title": "", "data": {"layout": v.get("layout") if v.get("layout") in LAYOUTS else random.choice(LAYOUTS),
                       "camera": random.choice(composer.C_CAMS), "transition": "cut", "elements": out},
                       "meta": {"i": i, "n": len(content["slides"]) + 1, "topic": "", "seed": random.randrange(1, 2 ** 31)}})
        t = end + 0.4
    n = int(t * 100) + 1
    audio = {"duration": t, "bpm": 120.0, "beat_period": 0.5, "time_signature": 4, "beats": [k * 0.5 for k in range(int(t * 2))],
             "downbeats": [k * 2.0 for k in range(int(t / 2))], "sections": [], "fps": 100, "notes": "carousel stills",
             "onsets": {"all": [], "vocal": [], "drums": [], "other": []},
             **{k: [0.0] * n for k in ("rms", "vocal", "low", "mid", "high", "drums", "bass", "other")}}
    times = [ln["end"] for ln in lines]
    return {"source": "carousel_lane", "lines": lines, "scenes": scenes, "style": genome}, audio, times


def render_heroes(content, genome, work, labels=True):
    """Renders one 3D still per slide with the engine (original data files are restored afterwards)."""
    data = BASE / "data"
    data.mkdir(exist_ok=True)
    keep = {f: (data / f).read_bytes() for f in ("lyrics.json", "audio.json") if (data / f).exists()}
    ly, au, times = fake_timeline(content, genome, labels)
    try:
        (data / "lyrics.json").write_text(json.dumps(ly, ensure_ascii=False), encoding="utf-8")
        (data / "audio.json").write_text(json.dumps(au), encoding="utf-8")
        out = work / "stills"
        shutil.rmtree(out, ignore_errors=True)
        subprocess.run([tool("bun"), "scripts/render.ts", "stills", "--t", ",".join(f"{x:.2f}" for x in times), "--samples", "2",
                        "--out", str(out)], cwd=BASE / "app", env=env_with_tools(), check=True, capture_output=True)
        return sorted(out.glob("*.png"), key=lambda p: float(p.stem.split("_")[1]))
    finally:
        for f, b in keep.items():
            (data / f).write_bytes(b)


def design(content, fmt, genome, heroes, work):
    pal = covers._palette({"style": genome})
    badge = FORMATS[fmt][0]
    n = len(content["slides"]) + 2
    paths = []

    def base(i, hero_y=0, hero_h=700):
        img = Image.new("RGB", (W, H), pal["ink"])
        if i < len(heroes):
            covers._band(img, Image.open(heroes[i]).convert("RGB").resize((1080, 1920)), hero_y, hero_h, pal["ink"])
        d = ImageDraw.Draw(img)
        d.text((W - 150, 50), f"{len(paths) + 1}/{n}", font=covers._font(34, "label"), fill=pal["ash"])
        return img, d

    img = Image.new("RGB", (W, H), pal["ink"])                                    # cover: text first, hero below it
    d = ImageDraw.Draw(img)
    d.text((70, 120), badge, font=covers._font(44, "label"), fill=pal["signal"])
    f, lines = covers._fit(d, content["title"].upper(), 940, 4, 110)
    y = covers._text_block(d, lines, f, 70, 190, pal["bone"])
    sf, sl = covers._fit(d, content.get("subtitle", ""), 940, 2, 40, "body", 30)
    y = covers._text_block(d, sl, sf, 70, y + 20, pal["ash"])
    if heroes:
        hy = int(y + 40)
        covers._band(img, Image.open(heroes[0]).convert("RGB").resize((1080, 1920)), hy, max(380, 1210 - hy), pal["ink"])
        d = ImageDraw.Draw(img)
    d.text((W - 150, 50), f"1/{n}", font=covers._font(34, "label"), fill=pal["ash"])
    d.text((70, 1240), "SWIPE  ->", font=covers._font(42, "label"), fill=pal["signal"])
    paths.append(img)
    for k, s in enumerate(content["slides"], 1):                                   # content slides
        img, d = base(k, 0, 640)
        y = 680
        if fmt == "mythfact":
            v = str(s.get("verdict", "MYTH")).upper()
            col = (230, 70, 70) if v == "MYTH" else (60, 200, 140)
            d.rectangle([70, y, 70 + d.textlength(v, font=covers._font(40, "head")) + 40, y + 62], fill=col)
            d.text((90, y + 8), v, font=covers._font(40, "head"), fill=(255, 255, 255))
            y += 90
        else:
            d.text((70, y), f"{k:02d}", font=covers._font(52, "head"), fill=pal["signal"])
            y += 72
        hf, hl = covers._fit(d, str(s["heading"]).upper(), 940, 2, 68)
        y = covers._text_block(d, hl, hf, 70, y, pal["bone"]) + 18
        if fmt == "versus":
            for name, val in ((content.get("a"), s.get("a")), (content.get("b"), s.get("b"))):
                d.text((70, y), str(name or "").upper(), font=covers._font(34, "label"), fill=pal["signal"])
                vf, vl = covers._fit(d, str(val or ""), 700, 2, 40, "body", 30)
                y = covers._text_block(d, vl, vf, 330, y - 2, pal["bone"], gap=1.2) + 22
        else:
            bf, bl = covers._fit(d, str(s.get("body", "")), 940, 5, 40, "body", 30)
            covers._text_block(d, bl, bf, 70, y, pal["ash"], gap=1.3)
        paths.append(img)
    img, d = base(len(heroes) - 1, 640, 710)                                      # takeaway + follow
    d.text((70, 140), "THE TAKEAWAY", font=covers._font(44, "label"), fill=pal["signal"])
    tf, tl = covers._fit(d, content.get("takeaway", ""), 940, 4, 70)
    y = covers._text_block(d, tl, tf, 70, 210, pal["bone"])
    d.text((70, y + 40), "Save this  ·  Follow @datavelvet for 3D tech explained daily", font=covers._font(36, "body"), fill=pal["ash"])
    paths.append(img)
    out = []
    for k, im in enumerate(paths, 1):
        p = work / f"slide_{k:02d}.jpg"
        im.save(p, quality=92)
        out.append(p)
    return out


def refresh_stats(cs):
    """Instagram saves/shares/reach for carousels older than a day (the style picker learns from them)."""
    import os
    import requests
    tok = os.getenv("IG_ACCESS_TOKEN", "").strip()
    now = datetime.now(timezone.utc)
    for p in cs["posts"]:
        if not tok or not p.get("instagram_id") or p.get("stats") or (now - datetime.fromisoformat(p["time"])).total_seconds() < 86400:
            continue
        try:
            r = requests.get(f"https://graph.instagram.com/v21.0/{p['instagram_id']}/insights", timeout=30,
                             params={"metric": "reach,saved,shares,likes", "access_token": tok})
            if r.ok:
                p["stats"] = {m["name"]: int((m.get("values") or [{}])[0].get("value", 0)) for m in r.json().get("data", [])}
        except Exception as e:
            print(f"  carousel stats unavailable ({e})")


def pick_style(cs):
    """Alternates 3D and presentation-deck carousels; once both have 3+ rated posts, leans 70% toward the one people save."""
    rated = {}
    for p in cs["posts"]:
        st = p.get("stats") or {}
        if st.get("reach"):
            rated.setdefault(p.get("style", "deck"), []).append((st.get("saved", 0) + st.get("shares", 0)) / st["reach"])
    last = (cs["posts"][-1] if cs["posts"] else {}).get("style")
    alt = "deck" if last == "3d" else "3d"
    if all(len(rated.get(k, [])) >= 3 for k in ("3d", "deck")):
        best = max(("3d", "deck"), key=lambda k: sum(rated[k]) / len(rated[k]))
        return best if random.random() < 0.7 else alt
    return alt


def dev_topic(cs, state):
    """Developer lane: the best-performing Shorts first (their audience already proved it cares), then the famous-topics list."""
    done = {str(p.get("source_topic") or p["topic"]).lower() for p in cs["posts"]}

    def rank(p):
        st = p.get("stats") or {}
        return st.get("score") or (st.get("yt_views", 0) + st.get("ig_views", 0))
    for p in sorted(state.get("posts", []), key=rank, reverse=True)[:12]:
        if p.get("topic") and p["topic"].lower() not in done and rank(p) > 0:
            return p["topic"], True
    for t in json.loads((BASE / "topics_deep.json").read_text(encoding="utf-8")):
        if t.lower() not in done and t.lower() not in {u.lower() for u in state.get("used_topics", [])}:
            return t, False
    return None, False


def make(topic=None, fmt=None, post=False, at=None):
    cs, state = load_cs(), load_state()
    if post:                                       # one carousel per Eastern day (a late scheduled run after a manual one skips)
        from zoneinfo import ZoneInfo
        today = datetime.now(ZoneInfo("America/Toronto")).date()
        if any(datetime.fromisoformat(p["time"]).astimezone(ZoneInfo("America/Toronto")).date() == today for p in cs["posts"]):
            print("⏭️ Today's carousel is already posted - skipping")
            return []
    used = {p["topic"].lower() for p in cs["posts"]} | {t.lower() for t in state.get("used_topics", [])}
    recent = [p.get("format") for p in cs["posts"][-3:]]
    dev, from_short = os.getenv("CAROUSEL_LANE", "dev") == "dev" and not topic, False
    if dev:
        topic, from_short = dev_topic(cs, state)
        dev = bool(topic)
    pool = DEV_FORMATS if dev else list(FORMATS)
    fmt = fmt or random.choice([f for f in pool if f not in recent] or pool)
    topic = topic or next((t for t in random.sample(IDEAS[fmt], len(IDEAS[fmt])) if t.lower() not in used), None)
    if not topic:
        topic = json.loads(writer.llm(f'Suggest ONE new everyday-tech carousel topic for the format "{FORMATS[fmt][1]}", not one of: '
                                      f'{", ".join(list(used)[-80:])}. Return ONLY JSON: {{"topic": "..."}}', label="carousel topic"))["topic"]
    refresh_stats(cs)
    style = pick_style(cs)
    print(f"🗂️ Carousel ({style}): {FORMATS[fmt][0]} - {topic}")
    if style == "3d":                              # 3D objects as backgrounds, real charts, 5 dense slides
        import carousel3d
        slides = carousel3d.make(topic, fmt, dev)
        content = json.loads((slides[0].parent / "content.json").read_text(encoding="utf-8"))
        return _publish(cs, content, slides, topic, fmt, style, "-", post, at, dev, from_short)
    content = write_content(topic, fmt, dev)
    work = BASE / "out" / "carousels" / f"{time.strftime('%Y%m%d-%H%M%S')}_{fmt}"
    work.mkdir(parents=True, exist_ok=True)
    (work / "content.json").write_text(json.dumps(content, indent=2, ensure_ascii=False), encoding="utf-8")
    last_theme = (cs["posts"][-1] if cs["posts"] else {}).get("theme")
    theme = random.choice([t for t in deck.THEMES if t != last_theme])
    slides = deck.Deck(content, fmt, theme, FORMATS[fmt][0]).build(work)     # presentation-style slide deck
    print(f"✅ {len(slides)} slides in {work}")
    return _publish(cs, content, slides, topic, fmt, "deck", theme, post, at, dev, from_short)


def _publish(cs, content, slides, topic, fmt, style, theme, post, at, dev=False, from_short=False):
    if post:
        if at:                                     # made early; post exactly at the slot time (Eastern)
            subprocess.run([__import__("sys").executable, str(BASE / "wait_until.py"), at], check=False)
        from instagram_upload import upload_carousel
        cap = (content.get("caption", "") + ("\n\nThe full 60-second breakdown is on our latest Reel." if from_short else "") + ("\n\nSources: " + ", ".join(s.split("/")[2] for s in content.get("sources", [])[:3] if "//" in s)
                                             if content.get("sources") else ""))[:2150]
        pid = upload_carousel([str(p) for p in slides], cap)
        cs["posts"].append({"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "topic": topic, "format": fmt, "theme": theme,
                            "style": style, "lane": "dev" if dev else "general", "source_topic": topic if dev else None,
                            "instagram_id": pid})
        STATE.write_text(json.dumps(cs, indent=2, ensure_ascii=False), encoding="utf-8")
    return slides


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--format", choices=list(FORMATS))
    ap.add_argument("--topic")
    ap.add_argument("--post", action="store_true")
    ap.add_argument("--at", help="post at this Eastern time, e.g. 11:00 (waits after making the slides)")
    a = ap.parse_args()
    make(a.topic, a.format, a.post, a.at)
