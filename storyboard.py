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

SERIES = {
    "How It Works": "Curiosity-driven: open with a surprising fact about something people use every day, then reveal "
                    "what really happens under the hood, step by step.",
    "Interview Prep": "Frame the topic as a classic technical interview question (\"You're asked: ...\"). Explain it step "
                      "by step, then end with the model answer to say in the interview. Never claim a specific company "
                      "asked it unless that is widely documented - say \"a classic interview question\" instead.",
    "System Design": "Frame it as designing or scaling a real system: start with the problem at scale (users, requests, "
                     "data), then build the architecture piece by piece and show where it breaks and how it is fixed.",
}

PROMPT = """You write scripts for a faceless YouTube Shorts / Instagram Reels channel that teaches software
engineering and computer science concepts step by step with high-motion 3D diagram animations.

Topic: "{topic}"
Series: "{series}" - {series_brief}
{insights}{feedback}
THE NARRATION: a friendly senior engineer talking to one person. Casual, confident, plain English, short
sentences, contractions, a little personality. No hype words, no emojis, no "in this video". The FIRST sentence is
the hook: under 12 words, bold and specific, it must stop the scroll in the first second (a surprising claim,
a mistake people make, or a question they can't answer). Teach it step by step with one concrete real-world example, end with a one-line recap
("say this in the interview" style) and "Follow for more." Write numbers and symbols the way they are SPOKEN
("google dot com", "ten megabytes") because the narration is read by a text-to-speech voice.

THE VISUALS: each scene is a small 3D system diagram on a floor grid, seen from above at an angle, on a
TALL phone screen. The animation must show exactly what the narrator is saying at that moment.

JSON format - return ONLY: {{"topic": "...", "hooks": [...], "scenes": [...], "youtube": {{...}}, "instagram_caption": "..."}}

"hooks": 3 different on-screen hook lines for the first second of the video, max 6 words each, punchy, no emojis
(e.g. "Your RAM is lying to you", "90% of devs get this wrong"). They are shown in giant text while the first
sentence is spoken, so they must match its meaning. Wrap the single most important word in **double asterisks**.

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
- "youtube": {{"title": max 60 chars, curiosity-driven (do not add the series name or #shorts - added automatically),
   "description": 2-3 sentences + 5-7 hashtags, "tags": 6-10 strings}}
- "instagram_caption": 2-4 short lines + a "save this" call to action + 6-8 hashtags.
"""


REVIEW = """You are a strict senior technical editor reviewing a script for a short educational video before it is
published to thousands of developers. Topic: "{topic}". Series: "{series}".

SCRIPT (numbered scenes, then on-screen text):
{script}

HOOK OPTIONS:
{hooks}

This is a ~2 minute SHORT for beginners, so normal simplifications and skipped sub-steps are FINE.
Separate real errors from nitpicks:
- "critical_errors": ONLY statements an expert would call outright WRONG (wrong mechanism, wrong order of steps,
  wrong numbers, made-up claims about specific companies). Not simplifications, not missing detail, not wording.
- "minor_issues": simplifications, missing nuance, awkward wording, weak hook - things that would make it better.
Also judge: does it teach the topic clearly step by step, and is the first sentence a strong scroll-stopping hook?

Return ONLY JSON: {{"score": 1-10 overall quality, "critical_errors": ["what is wrong + the correct fact", ...],
"minor_issues": ["...", ...], "best_hook": index of the strongest hook option (0-based)}}"""


def _script_text(sb):
    lines = []
    for i, sc in enumerate(sb["scenes"]):
        lines.append(f"{i + 1}. [{sc['title']}] {sc['narration']}")
    extras = [b.get("text") for sc in sb["scenes"] for b in sc["beats"] if b.get("text")]
    extras += [o["label"] + (f" ({o['sub']})" if o.get("sub") else "") for sc in sb["scenes"] for o in sc["objects"]]
    return "\n".join(lines) + "\nON-SCREEN TEXT: " + "; ".join(dict.fromkeys(extras))


def review(sb, series, key):
    """Quality gate: a second model pass fact-checks and scores the script."""
    hooks = "\n".join(f"{i}. {h}" for i, h in enumerate(sb.get("hooks", [])))
    text = _gemini(REVIEW.format(topic=sb["topic"], series=series, script=_script_text(sb), hooks=hooks or "(none)"), key,
                   label="quality gate review")
    data = json.loads(re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.M).strip())
    return {"score": int(data.get("score", 0)), "factual_errors": [str(x) for x in data.get("critical_errors") or []],
            "other_issues": [str(x) for x in data.get("minor_issues") or []], "best_hook": int(data.get("best_hook", 0) or 0)}


# Fallbacks when Gemini doesn't answer, in priority order (OpenAI-compatible APIs).
# OpenRouter: free models first (the account has no credits); OpenCode needs account funds to work.
FALLBACKS = [
    ("OpenRouter", "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY",
     ["nvidia/nemotron-3-ultra-550b-a55b:free", "nvidia/nemotron-3-super-120b-a12b:free", "nvidia/nemotron-3.5-lightning:free"]),
    ("Groq", "https://api.groq.com/openai/v1", "GROQ_API_KEY", ["openai/gpt-oss-120b", "qwen/qwen3.8-27b"]),
    ("OpenCode", "https://opencode.ai/zen/v1", "OPENCODE_API_KEY", ["gemini-3.8-flash", "claude-sonnet-5-5", "gpt-5.4-mini"]),
]


def _json_text(text):
    """Strip reasoning blocks / code fences and return just the outermost JSON object."""
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()
    text = re.sub(r"^```(json)?|```$", "", text, flags=re.M).strip()
    a, b = text.find("{"), text.rfind("}")
    return text[a:b + 1] if a != -1 and b > a else text


def _openai_compatible(name, base, key, model, prompt):
    r = requests.post(f"{base}/chat/completions", headers={"Authorization": f"Bearer {key}"}, timeout=300, json={
        "model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.7,
        "max_tokens": 5000 if name == "Groq" else 12000, "response_format": {"type": "json_object"}})
    data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if r.status_code != 200 or "choices" not in data:
        raise RuntimeError(f"{r.status_code}: {r.text[:160]}")
    text = data["choices"][0]["message"].get("content") or ""
    json.loads(_json_text(text))   # must be valid JSON, otherwise try the next model
    return text


def _gemini(prompt, key, label="storyboard"):
    """Ask Gemini; if it fails, fall back to OpenRouter -> Groq -> OpenCode (in that order)."""
    last = None
    for attempt in range(2):
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
                    print(f"  {label} by {model}")
                    return _json_text(text)
                last = f"{model} {r.status_code}: {r.text[:160]}"
                print(f"  {last}")
            except Exception as e:
                last = f"{model}: {e}"
                print(f"  {last}")
        if attempt == 0:
            time.sleep(15)
    print("  Gemini unavailable - trying fallback models")
    for name, base, env, models in FALLBACKS:
        fkey = os.getenv(env, "").strip()
        if not fkey:
            continue
        for model in models:
            try:
                text = _openai_compatible(name, base, fkey, model, prompt)
                print(f"  {label} by {name} / {model}")
                return _json_text(text)
            except Exception as e:
                last = f"{name}/{model}: {e}"
                print(f"  {last}")
    raise RuntimeError(f"All models failed (Gemini + fallbacks): {last}")


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
    hooks = [_cut(re.sub(r"\s+", " ", str(h)), 48) for h in (sb.get("hooks") or []) if str(h).strip()][:3]
    return {
        "topic": sb.get("topic", ""),
        "hooks": hooks,
        "hook": sb.get("hook") or (hooks[0] if hooks else ""),
        "scenes": clean,
        "youtube": {"title": title, "description": str(yt.get("description", ""))[:4500],
                    "tags": [str(t)[:30] for t in (yt.get("tags") or [])][:12]},
        "instagram_caption": str(sb.get("instagram_caption", ""))[:2100],
    }


def write_storyboard(topic, series="How It Works", insights="", key=None, tries=3):
    """Write a storyboard, then pass it through the quality gate; retry with the reviewer's notes if it fails."""
    key = key or os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    feedback, err, best = "", None, None
    for i in range(tries):
        prompt = PROMPT.format(topic=topic, series=series, series_brief=SERIES.get(series, ""), insights=insights,
                               feedback=feedback, types=list(OBJ_TYPES), colors=list(PALETTE), example=EXAMPLE)
        text = _gemini(prompt, key).strip()
        try:
            if text.startswith("```"):
                text = re.sub(r"^```(json)?|```$", "", text, flags=re.M).strip()
            sb = validate(json.loads(text))
        except Exception as e:
            err = e
            print(f"  storyboard attempt {i + 1} rejected: {e}")
            continue
        try:
            rv = review(sb, series, key)
        except Exception as e:
            print(f"  quality gate unavailable ({e}) - accepting the validated draft")
            return sb
        print(f"  quality gate: score {rv['score']}/10, {len(rv['factual_errors'])} real error(s), {len(rv['other_issues'])} minor note(s)")
        if sb["hooks"]:
            sb["hook"] = sb["hooks"][min(max(rv["best_hook"], 0), len(sb["hooks"]) - 1)]
        sb["review"] = rv
        if not rv["factual_errors"] and rv["score"] >= 7:
            return sb
        if not rv["factual_errors"] and (best is None or rv["score"] > best["review"]["score"]):
            best = sb
        err = "; ".join(rv["factual_errors"] + rv["other_issues"])[:600]
        print(f"  quality gate rejected draft {i + 1}: {err}")
        feedback = ("\nA senior editor REJECTED the previous draft of this script. Fix every point:\n- "
                    + "\n- ".join(rv["factual_errors"] + rv["other_issues"]) + "\n")
    if best is not None:
        print(f"  using best fact-checked draft (score {best['review']['score']}/10)")
        return best
    raise RuntimeError(f"Could not get a storyboard past the quality gate: {err}")


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
