"""
Storyboard writer: turns a topic into a scene-by-scene 3D diagram explainer (JSON) using Gemini,
validates it, and falls back to the hand-written storyboards/ bank if Gemini is unavailable.

Every animation is a "beat" tied to a cue phrase in the narration, so the renderer can fire it
at the exact moment those words are spoken.
"""
import json
import os
import re
import time
from pathlib import Path

import requests

from motion3d import BEAT_TYPES, OBJ_TYPES, PALETTE, norm_word

BASE = Path(__file__).parent
TOPICS_FILE = BASE / "explainer_topics.json"
STATE_FILE = BASE / "state.json"
BANK_DIR = BASE / "storyboards"

MODELS = ["gemini-3.5-flash", "gemini-3.8-flash", "gemini-flash-latest", "gemini-3.1-flash-lite", "gemini-2.5-flash"]

EXAMPLE = """{"kicker": "the root", "title": "Start at the very top",
 "narration": "The resolver doesn't know either. So it starts at the top, with a root server. The root doesn't know Google, but it knows who handles every dot com address.",
 "objects": [{"id": "pc", "type": "laptop", "pos": [0, -3.4], "label": "You", "sub": "laptop"},
             {"id": "resolver", "type": "server", "pos": [0, 0], "label": "Resolver", "sub": "run by your ISP"},
             {"id": "root", "type": "server", "pos": [-2.6, 3.4], "label": "Root server", "sub": "13 worldwide", "color": "purple"}],
 "links": [{"from": "pc", "to": "resolver"}],
 "beats": [{"cue": "root server", "do": "show", "ids": ["root"]},
           {"cue": "starts at the top", "do": "send", "from": "resolver", "to": "root", "label": "google.com?"},
           {"cue": "the root doesn't", "do": "focus", "ids": ["root", "resolver"]},
           {"cue": "who handles", "do": "send", "from": "root", "to": "resolver", "label": "ask .com", "color": "purple"},
           {"cue": "dot com address", "do": "text", "text": "Try the .com servers", "color": "purple"}]}"""

PROMPT = """You write scripts for a faceless YouTube Shorts / Instagram Reels channel that teaches software
engineering and computer science concepts step by step with high-motion 3D diagram animations.

Topic: "{topic}"

THE NARRATION: a friendly senior engineer talking to one person. Casual, confident, plain English, short
sentences, contractions, a little personality. No hype words, no emojis, no "in this video". First sentence is
a curiosity hook. Teach it step by step with one concrete real-world example, end with a one-line recap
("say this in the interview" style) and "Follow for more." Write numbers and symbols the way they are SPOKEN
("google dot com", "ten megabytes") because the narration is read by a text-to-speech voice.

THE VISUALS: each scene is a small 3D system diagram on a floor grid, seen from above at an angle, on a
TALL phone screen. The animation must show exactly what the narrator is saying at that moment.

JSON format - return ONLY: {{"topic": "...", "scenes": [...], "youtube": {{...}}, "instagram_caption": "..."}}

Each scene:
- "kicker": section name, 2-3 lowercase words. Consecutive scenes of one section repeat it.
- "title": on-screen headline for THIS step, max 34 chars, sentence case, different for every scene.
- "narration": 1-4 sentences, 15-45 words.
- "objects": 1-6 things on the floor: {{"id": short_snake_id, "type": one of {types}, "pos": [x, z],
     "label": max 14 chars, "sub": optional max 20 chars, "color": optional one of {colors},
     "count": for cubes/queue only (1-12), "w": for layer only (width 3-8)}}
   Layout for a TALL screen: x from -3 to 3, z from -3.5 (near, bottom of screen) to 3.5 (far, top).
   Keep at least 2.4 units between objects. Prefer vertical flows (bottom -> top) and rows of max 3 across.
   Re-use the same id, type and pos for the same thing in consecutive scenes so it stays put on screen.
   type guide: server=any backend/service, db=database/storage, user=a person, laptop/phone/screen=client device,
   chip=CPU/hardware/core, cubes=data items/memory blocks/records, queue=messages/requests waiting in line,
   layer=a wide platform (OS, kernel, network, cluster) - things running ON it use the same z and stand on top,
   cloud=internet/cloud, router=network device,
   lock=security/encryption, doc=file/document, globe=world/internet, sphere=abstract node, box=anything else.
- "links": optional static connections already present: [{{"from": id, "to": id, "label": optional max 14 chars}}]
- "beats": 3-6 animation actions, each fired when its "cue" is spoken. "cue" MUST be 1-4 words copied EXACTLY
   from this scene's narration, in the order they are spoken. Actions:
   {{"do": "show", "ids": [...]}}             object pops in (objects without a show beat appear at scene start)
   {{"do": "send", "from": id, "to": id, "label": max 18 chars, "color": optional}}   a glowing packet flies between them
   {{"do": "flow", "from": id, "to": id}}     continuous stream of packets along a link
   {{"do": "connect", "from": id, "to": id, "label": optional}}   a link draws itself
   {{"do": "highlight", "ids": [...]}}        object lifts and glows
   {{"do": "break", "ids": [...]}}            object turns red, shakes, "CRASHED"
   {{"do": "focus", "ids": [...]}}            camera flies in on those objects
   {{"do": "reset"}}                          camera back to the whole diagram
   {{"do": "text", "text": max 30 chars, "color": optional}}   big callout card (key fact, number, definition)
   {{"do": "set", "id": id, "label": optional, "sub": optional, "color": optional}}   change an object's text/colour
   {{"do": "count", "id": id, "n": number}}   cubes/queue grows to n items
   Every scene needs motion: at least one send/flow/connect/highlight/break/count beat. Use "text" for the key
   takeaway of the step. Use "send" whenever something is requested, returned, written, copied or moved.

Example scene:
{example}

Rules:
- 9 to 12 scenes, total narration 260-340 words (about 100-140 seconds).
- Facts must be accurate; numbers realistic.
- "youtube": {{"title": max 70 chars + " #shorts", "description": 2-3 sentences + 5-7 hashtags, "tags": 6-10 strings}}
- "instagram_caption": 2-4 short lines + a "save this" call to action + 6-8 hashtags.
"""


def _gemini(prompt, key):
    last = None
    for attempt in range(3):
        for model in MODELS:
            try:
                r = requests.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                    headers={"x-goog-api-key": key},
                    json={"contents": [{"parts": [{"text": prompt}]}],
                          "generationConfig": {"responseMimeType": "application/json", "temperature": 0.8}},
                    timeout=240)
                if r.status_code == 200:
                    parts = r.json()["candidates"][0]["content"]["parts"]
                    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
                    print(f"  storyboard written by {model}")
                    return text
                last = f"{model} {r.status_code}: {r.text[:160]}"
                print(f"  {last}")
            except Exception as e:
                last = f"{model}: {e}"
                print(f"  {last}")
        time.sleep(20 * (attempt + 1))
    raise RuntimeError(f"All Gemini models failed: {last}")


def _cut(s, n):
    s = str(s or "").strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _num(v, lo, hi, default):
    try:
        return max(lo, min(hi, float(v)))
    except (TypeError, ValueError):
        return default


def _cue_ok(cue, narration):
    toks = [norm_word(w) for w in str(cue).split() if norm_word(w)]
    words = [norm_word(w) for w in narration.split() if norm_word(w)]
    return bool(toks) and any(words[i:i + len(toks)] == toks for i in range(len(words) - len(toks) + 1))


def _clean_scene(sc):
    narration = re.sub(r"\s+", " ", str(sc.get("narration", ""))).strip()
    if len(narration.split()) < 5:
        raise ValueError("scene with empty narration")
    out = {"kicker": _cut(str(sc.get("kicker", "")).lower(), 24), "title": _cut(sc.get("title"), 40), "narration": narration}

    objs = []
    for o in (sc.get("objects") or [])[:7]:
        if not isinstance(o, dict) or not o.get("id"):
            continue
        pos = o.get("pos") or [0, 0]
        c = {"id": re.sub(r"[^a-z0-9_]", "_", str(o["id"]).lower())[:24],
             "type": o.get("type") if o.get("type") in OBJ_TYPES else "box",
             "pos": [_num(pos[0] if len(pos) > 0 else 0, -4.5, 4.5, 0), _num(pos[-1] if len(pos) > 1 else 0, -5, 5, 0)],
             "label": _cut(o.get("label"), 18), "sub": _cut(o.get("sub"), 24)}
        if o.get("color") in PALETTE:
            c["color"] = o["color"]
        if c["type"] in ("cubes", "queue"):
            c["count"] = int(_num(o.get("count"), 1, 12, 4))
        if c["type"] == "layer":
            c["w"] = _num(o.get("w"), 3, 9, 6)
        if o.get("y"):
            c["y"] = _num(o["y"], 0, 3, 0)
        if c["id"] not in [x["id"] for x in objs]:
            objs.append(c)
    out["objects"] = objs
    ids = {o["id"] for o in objs}

    def fix(i):
        return re.sub(r"[^a-z0-9_]", "_", str(i).lower())[:24]

    out["links"] = [{"from": fix(l["from"]), "to": fix(l["to"]), "label": _cut(l.get("label"), 16)}
                    for l in (sc.get("links") or []) if isinstance(l, dict) and fix(l.get("from")) in ids and fix(l.get("to")) in ids]
    beats = []
    for b in (sc.get("beats") or [])[:8]:
        if not isinstance(b, dict) or b.get("do") not in BEAT_TYPES or not _cue_ok(b.get("cue", ""), narration):
            continue
        nb = {"cue": str(b["cue"]), "do": b["do"]}
        if b["do"] in ("show", "hide", "highlight", "break", "focus"):
            nb["ids"] = [fix(i) for i in (b.get("ids") or []) if fix(i) in ids]
            if not nb["ids"]:
                continue
        elif b["do"] in ("send", "flow", "connect"):
            nb["from"], nb["to"] = fix(b.get("from")), fix(b.get("to"))
            if nb["from"] not in ids or nb["to"] not in ids or nb["from"] == nb["to"]:
                continue
            nb["label"] = _cut(b.get("label"), 20)
        elif b["do"] == "text":
            if not b.get("text"):
                continue
            nb["text"] = _cut(b["text"], 34)
        elif b["do"] in ("set", "count"):
            nb["id"] = fix(b.get("id"))
            if nb["id"] not in ids:
                continue
            if b["do"] == "count":
                nb["n"] = int(_num(b.get("n"), 1, 12, 4))
            else:
                for k, n in (("label", 18), ("sub", 24)):
                    if b.get(k):
                        nb[k] = _cut(b[k], n)
        if b.get("color") in PALETTE:
            nb["color"] = b["color"]
        beats.append(nb)
    out["beats"] = beats
    if isinstance(sc.get("camera"), dict):
        out["camera"] = sc["camera"]
    return out


def validate(sb):
    """Clean the storyboard and reject ones that would make a weak or broken video."""
    scenes = sb.get("scenes") or []
    if not 6 <= len(scenes) <= 14:
        raise ValueError(f"bad scene count {len(scenes)}")
    clean = [_clean_scene(sc) for sc in scenes]
    titles = [s["title"] for s in clean]
    if any(not t for t in titles):
        raise ValueError("scene without a title")
    if len(set(titles)) < len(titles) * 0.7:
        raise ValueError("scene titles repeat - each step needs its own headline")
    if sum(1 for s in clean if s["objects"]) < len(clean) * 0.8:
        raise ValueError("too few scenes with 3D objects")
    if sum(1 for s in clean if len(s["beats"]) >= 2) < len(clean) * 0.7:
        raise ValueError("too few animation beats matched to the narration")
    motion = {"send", "flow", "connect", "highlight", "break", "count"}
    if sum(1 for s in clean for b in s["beats"] if b["do"] in motion) < len(clean):
        raise ValueError("not enough motion")
    words = sum(len(s["narration"].split()) for s in clean)
    if not 170 <= words <= 420:
        raise ValueError(f"narration length {words} words out of range")
    yt = sb.get("youtube") or {}
    title = _cut(yt.get("title") or sb.get("topic", "Explained"), 95)
    if "#shorts" not in title.lower():
        title = _cut(title, 86) + " #shorts"
    return {
        "topic": sb.get("topic", ""),
        "scenes": clean,
        "youtube": {"title": title, "description": str(yt.get("description", ""))[:4500],
                    "tags": [str(t)[:30] for t in (yt.get("tags") or [])][:12]},
        "instagram_caption": str(sb.get("instagram_caption", ""))[:2100],
    }


def write_storyboard(topic, key=None, tries=3):
    key = key or os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    prompt = PROMPT.format(topic=topic, types=list(OBJ_TYPES), colors=list(PALETTE), example=EXAMPLE)
    err = None
    for i in range(tries):
        text = _gemini(prompt, key).strip()
        try:
            if text.startswith("```"):
                text = re.sub(r"^```(json)?|```$", "", text, flags=re.M).strip()
            return validate(json.loads(text))
        except Exception as e:
            err = e
            print(f"  storyboard attempt {i + 1} rejected: {e}")
    raise RuntimeError(f"Could not get a valid storyboard: {err}")


# ---------- topic queue ----------
def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"used_topics": [], "used_bank": [], "posts": []}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def next_topic(state):
    topics = json.loads(TOPICS_FILE.read_text(encoding="utf-8"))
    fresh = [t for t in topics if t not in state["used_topics"]]
    if not fresh:
        print("All topics used - starting the list again")
        state["used_topics"] = []
        fresh = topics
    return fresh[0]


def bank_storyboard(state):
    """A hand-written storyboard that hasn't been posted yet (used when Gemini is down)."""
    for p in sorted(BANK_DIR.glob("*.json")):
        if p.stem not in state["used_bank"]:
            return p.stem, validate(json.loads(p.read_text(encoding="utf-8")))
    return None, None
