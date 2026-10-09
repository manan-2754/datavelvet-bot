"""
Script writer for motion-graphics explainers: an LLM (Gemini -> OpenRouter -> Groq -> OpenCode -> Gemini Lite) picks,
for every scene, the visual format that best fits what is being explained, then a validator enforces the format rules
(no layout twice in a video, never the same format sequence as an earlier video) and a second pass fact-checks it.
"""
import json
import os
import random
import re
import time

import requests

from mg import ICONS

MODELS = ["gemini-3.5-flash", "gemini-3.8-flash", "gemini-flash-latest"]
LITE_MODELS = ["gemini-3.1-flash-lite", "gemini-flash-lite-latest"]
FALLBACKS = [
    ("OpenRouter", "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY",
     ["nvidia/nemotron-3-ultra-550b-a55b:free", "nvidia/nemotron-3-super-120b-a12b:free", "nvidia/nemotron-3.5-lightning:free"]),
    ("Groq", "https://api.groq.com/openai/v1", "GROQ_API_KEY", ["openai/gpt-oss-120b", "qwen/qwen3.8-27b"]),
    ("OpenCode", "https://opencode.ai/zen/v1", "OPENCODE_API_KEY", ["gemini-3.8-flash", "claude-sonnet-5-5", "gpt-5.4-mini"]),
]

# layout -> (min items, max items, what it is for, item fields)
SPEC = {
    "steps":      (3, 5, "an ordered procedure (numbered cards joined by arrows)", "label, sub"),
    "flow":       (3, 4, "data / requests moving between components (zig-zag boxes, animated arrows)", "label, sub, icon"),
    "compare":    (3, 5, "two things side by side, one row per aspect; scene also needs left_title + right_title", "label (aspect), left, right"),
    "stat":       (1, 4, "one striking number (item 1 value like '90%' or '3,000' or '0.2s'), optional 1-3 supporting facts", "label, value, sub, icon"),
    "bars":       (3, 5, "quantities to compare (animated bar chart); every value MUST be a number, units allowed: '120 ms', '45%'", "label, value"),
    "cycle":      (3, 6, "a loop that repeats (circular nodes, arrows around the ring)", "label, sub, icon"),
    "tree":       (4, 7, "a hierarchy: item 1 is the root; others have parent = index of their parent (0 = root)", "label, sub, icon, parent"),
    "stack":      (3, 5, "layers built on each other, listed BOTTOM layer first", "label, sub, icon"),
    "grid":       (2, 6, "a set of parallel options / types / features (tiles)", "label, sub, icon"),
    "timeline":   (3, 5, "things in time order; value = when (year, 't=0', '50 ms', 'day 3')", "label, sub, value"),
    "hub":        (4, 7, "one central thing connected to many (item 1 = centre, others = spokes)", "label, sub, icon"),
    "funnel":     (3, 5, "something narrowing / filtering step by step (widest first)", "label, sub"),
    "code":       (1, 3, "a command, query or snippet typed in a terminal: item 1 = {label: window title, lines: 2-6 short code lines (max 38 chars), line_cues: one cue per line}; optional extra items = takeaway notes", "label, lines, line_cues / label, sub"),
    "definition": (1, 4, "introducing a term: item 1 label = the term, sub = a one-sentence definition (max 22 words); optional 1-3 key properties", "label, sub, icon"),
    "pipeline":   (3, 6, "a multi-stage pipeline / build / processing chain (tiles snake across the screen)", "label, sub, icon"),
    # holographic 3D diagrams (VR look: glowing wireframe objects, dotted live flows, moving camera)
    # object shape comes from the item icon: server, db, user, cloud, globe, lock, phone, laptop, cpu/gear (chip),
    # file (doc), code/search/chart (screen), layers; any other icon = a holo prism with that icon on its label
    "holo_flow":     (3, 5, "a request / data path through real components (left to right); packets stream between them; optional packet = short text riding the packet (e.g. 'GET /home')", "label, icon, packet"),
    "holo_hub":      (4, 7, "one central system talking to many (item 1 = centre); live two-way packet streams", "label, icon"),
    "holo_orbit":    (3, 6, "item 1 = the core (a holographic globe), others orbit it on dotted rings in real time", "label, icon"),
    "holo_layers":   (3, 5, "holographic glass layers (BOTTOM first) with a scanner beam passing through them", "label, icon"),
    "holo_cluster":  (3, 6, "item 1 = an entry point (load balancer, scheduler, router) dispatching work to the others; live load %", "label, icon"),
    "holo_pipeline": (3, 6, "stations on a loop; a data cube travels through every station and changes colour", "label, icon"),
    "holo_tree":     (4, 7, "a hierarchy floating in 3D: item 1 = root, others have parent = index of their parent (0 = root)", "label, icon, parent"),
    "holo_chart":    (3, 6, "holographic bar + line chart; every value MUST be numeric ('120 ms', '45%')", "label, value"),
    "holo_compare":  (2, 2, "exactly two things face to face on holo platforms, each with a numeric value and a short sub", "label, icon, value, sub"),
    "holo_timeline": (3, 5, "milestones along a glowing path; value = when (year, 't=0', 'day 3')", "label, value, icon"),
}
LAYOUTS3D = {k for k in SPEC if k.startswith("holo_")}

PROMPT = """You write scripts for a premium motion-graphics explainer channel (YouTube Shorts / Instagram Reels, 9:16).
Every scene is an animated presentation slide: shapes, connectors and counters appear EXACTLY when the narrator says them.
The look must feel like a $20,000 studio explainer - clean, confident, surprising.

Topic: "{topic}"

SCENE FORMATS (choose the one that best SHOWS what that scene explains):
{formats}

ICONS you may use (field "icon"): {icons}

RULES
- 1 hook scene + {n_lo} to {n_hi} content scenes. Scene 1 has layout "hook": "hook" = max 7 words of giant text with ONE
  key word wrapped in **double asterisks**; its narration is 1-2 punchy sentences that create curiosity.
- Content scenes: each uses a DIFFERENT layout (never repeat a layout in this video), at least {min_distinct} different layouts.
  At least 4 content scenes MUST use the holographic 3D formats (names starting with "holo_") - give their items fitting icons.
  Pick the format from the CONTENT - a sequence becomes steps/pipeline, numbers become stat/bars, a hierarchy becomes tree, etc.
{avoid}- Each content scene: "layout", "title" (max 34 chars), "narration" (2-3 short spoken sentences, 18-40 words),
  "items" (count must fit the format), optional "emphasis": [{{"item": index, "cue": "..."}}] to pulse an item when stressed.
- EVERY item has "cue": 1-3 words copied EXACTLY from that scene's narration, at the moment the item should appear.
  Items must appear in the order they are mentioned. Labels: max 22 chars. Subs: max 40 chars.
- The final scene recaps the key idea and its narration ends with "Follow for more."
- Total narration 170-260 words. Accurate, specific facts and real numbers only. Casual, clear, no emojis in narration.
- "youtube": {{"title": max 70 chars ending " #shorts", "description": 2 sentences + 5-6 hashtags, "tags": 6-8 strings}},
  "instagram_caption": 2-3 short lines + "Save this for later." + 6-8 hashtags.

Return ONLY JSON: {{"topic", "hook", "scenes": [{{"layout": "hook", "hook": "...", "narration": "..."}}, {{"layout", "title", "narration", "items": [...], ...}}], "youtube", "instagram_caption"}}
{feedback}"""

REVIEW = """You are a senior engineer and teacher reviewing a short explainer script before it is published.
Topic: "{topic}"

SCRIPT:
{script}

Check: (1) any statement, number or label that is technically WRONG, (2) does each on-screen format fit what the scene
explains, (3) is it clear for a curious beginner. Simplifications are fine. Return ONLY JSON:
{{"score": 1-10, "critical_errors": ["what is wrong + correct fact", ...], "minor_issues": ["...", ...]}}"""


def _json_text(text):
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()
    text = re.sub(r"^```(json)?|```$", "", text, flags=re.M).strip()
    a = text.find("{")
    if a == -1:
        return text
    try:
        _, end = json.JSONDecoder().raw_decode(text[a:])
        return text[a:a + end]
    except ValueError:
        b = text.rfind("}")
        return text[a:b + 1] if b > a else text


def _gemini_call(model, prompt, key):
    r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                      headers={"x-goog-api-key": key}, timeout=240,
                      json={"contents": [{"parts": [{"text": prompt}]}],
                            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.9}})
    if r.status_code != 200:
        raise RuntimeError(f"{r.status_code}: {r.text[:120]}")
    parts = r.json()["candidates"][0]["content"]["parts"]
    return "".join(p.get("text", "") for p in parts if not p.get("thought"))


def _openai_compatible(name, base, key, model, prompt):
    r = requests.post(f"{base}/chat/completions", headers={"Authorization": f"Bearer {key}"}, timeout=300, json={
        "model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.8,
        "max_tokens": 6000 if name == "Groq" else 12000, "response_format": {"type": "json_object"}})
    data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if r.status_code != 200 or "choices" not in data:
        raise RuntimeError(f"{r.status_code}: {r.text[:160]}")
    text = data["choices"][0]["message"].get("content") or ""
    json.loads(_json_text(text))
    return text


def llm(prompt, label="script"):
    """Gemini first; then OpenRouter -> Groq -> OpenCode; Gemini Lite as the very last resort."""
    key, last = os.getenv("GEMINI_API_KEY", "").strip(), None
    if key:
        for attempt in range(2):
            for model in MODELS:
                try:
                    text = _gemini_call(model, prompt, key)
                    print(f"  {label} by {model}")
                    return _json_text(text)
                except Exception as e:
                    last = f"{model}: {e}"
                    print(f"  {last}")
            if attempt == 0:
                time.sleep(15)
    print("  Gemini unavailable - trying fallback models")
    for name, base, env, models in FALLBACKS:
        fkey = os.getenv(env, "").strip()
        for model in (models if fkey else []):
            try:
                text = _openai_compatible(name, base, fkey, model, prompt)
                print(f"  {label} by {name} / {model}")
                return _json_text(text)
            except Exception as e:
                last = f"{name}/{model}: {e}"
                print(f"  {last}")
    for model in (LITE_MODELS if key else []):
        try:
            text = _gemini_call(model, prompt, key)
            print(f"  {label} by {model} (last resort)")
            return _json_text(text)
        except Exception as e:
            last = f"{model}: {e}"
    raise RuntimeError(f"All models failed: {last}")


def _norm(w):
    return "".join(ch for ch in w.lower() if ch.isalnum())


def _cue_ok(cue, narration):
    toks = [_norm(w) for w in str(cue).split() if _norm(w)]
    ws = [_norm(w) for w in narration.split() if _norm(w)]
    return bool(toks) and any(ws[i:i + len(toks)] == toks for i in range(len(ws) - len(toks) + 1))


def format_signature(scenes):
    """The visual format of a video: its layout sequence and item counts."""
    return "|".join(f"{s['layout']}:{len(s.get('items', []))}" for s in scenes)


def _clip(s, n):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


def validate(sc, used_formats=(), last_count=None):
    scenes = sc.get("scenes") or []
    if len(scenes) < 7 or scenes[0].get("layout") != "hook":
        raise ValueError("need a hook scene first and at least 6 content scenes")
    hook_sc = scenes[0]
    hook = _clip(hook_sc.get("hook") or sc.get("hook"), 60)
    if "**" not in hook:
        w = hook.split()
        hook = " ".join(w[:-1] + [f"**{w[-1]}**"]) if w else "**Watch** this"
    clean = [{"layout": "hook", "hook": hook, "title": "", "items": [],
              "narration": re.sub(r"\s+", " ", str(hook_sc.get("narration", ""))).strip()}]
    if len(clean[0]["narration"].split()) < 5:
        raise ValueError("hook narration too short")
    seen, bad_cues, n_items = set(), 0, 0
    for st in scenes[1:]:
        L = st.get("layout")
        if L not in SPEC:
            raise ValueError(f"unknown layout {L!r}")
        if L in seen:
            raise ValueError(f"layout {L!r} used twice - every scene needs a different format")
        seen.add(L)
        narration = re.sub(r"\s+", " ", str(st.get("narration", ""))).strip()
        if len(narration.split()) < 10:
            raise ValueError(f"scene '{st.get('title')}' narration too short")
        lo, hi = SPEC[L][:2]
        items = [it for it in (st.get("items") or []) if isinstance(it, dict)][:hi]
        if not lo <= len(items) <= hi:
            raise ValueError(f"{L} scene needs {lo}-{hi} items, got {len(items)}")
        out = []
        for j, it in enumerate(items):
            cue = str(it.get("cue", ""))
            n_items += 1
            if not _cue_ok(cue, narration):
                bad_cues += 1
                cue = ""
            o = {"label": _clip(it.get("label"), 26), "sub": _clip(it.get("sub"), 48), "cue": cue}
            if it.get("icon") in ICONS:
                o["icon"] = it["icon"]
            if it.get("packet"):
                o["packet"] = _clip(it.get("packet"), 18)
            if it.get("value") not in (None, ""):
                o["value"] = _clip(it.get("value"), 14)
            if L == "compare":
                o["left"], o["right"] = _clip(it.get("left"), 22), _clip(it.get("right"), 22)
                if not o["left"] or not o["right"]:
                    raise ValueError("compare rows need left and right")
            if L in ("tree", "holo_tree"):
                try:
                    o["parent"] = max(0, min(j - 1, int(it.get("parent", 0) or 0)))
                except (TypeError, ValueError):
                    o["parent"] = 0
            if L in ("bars", "holo_chart") and not re.search(r"\d", str(o.get("value", ""))):
                raise ValueError("every bars item needs a numeric value")
            if L == "code" and j == 0:
                lines = [_clip(x, 40) for x in (it.get("lines") or []) if str(x).strip()][:6]
                if len(lines) < 2:
                    raise ValueError("code scene needs 2-6 code lines")
                cues = list(it.get("line_cues") or [])
                o["lines"] = lines
                o["line_cues"] = [str(c) if _cue_ok(c, narration) else "" for c in (cues + [""] * len(lines))[:len(lines)]]
            if L == "stat" and j == 0 and not re.search(r"\d", str(o.get("value") or o["label"])):
                raise ValueError("stat scene needs a number in item 1")
            if L == "definition" and j == 0:
                o["sub"] = _clip(it.get("sub"), 160)
            out.append(o)
        emph = []
        for em in st.get("emphasis") or []:
            if isinstance(em, dict) and isinstance(em.get("item"), int) and 0 <= em["item"] < len(out) \
                    and _cue_ok(em.get("cue", ""), narration):
                emph.append({"item": em["item"], "cue": em["cue"]})
        s = {"layout": L, "title": _clip(st.get("title"), 40), "narration": narration, "items": out, "emphasis": emph}
        if L == "compare":
            s["left_title"] = _clip(st.get("left_title") or "Before", 16)
            s["right_title"] = _clip(st.get("right_title") or "After", 16)
        clean.append(s)
    if len(seen & LAYOUTS3D) < 4:
        raise ValueError(f"only {len(seen & LAYOUTS3D)} holo formats - use at least 4 of the holo_* formats")
    if len(seen) < 6:
        raise ValueError(f"only {len(seen)} different formats - use at least 6")
    if bad_cues > max(2, n_items * 0.25):
        raise ValueError(f"{bad_cues} item cues are not exact words from their scene narration")
    sig = format_signature(clean[1:])
    if sig in set(used_formats):
        raise ValueError("this exact format sequence was used in an earlier video - choose a different order or formats")
    if last_count is not None and len(clean) - 1 == last_count:
        raise ValueError(f"the previous video had {last_count} content scenes - use a different number of scenes")
    words = sum(len(s["narration"].split()) for s in clean)
    if not 150 <= words <= 300:
        raise ValueError(f"narration length {words} words (need 170-260)")
    if not re.search(r"follow for more", clean[-1]["narration"], re.I):
        clean[-1]["narration"] = clean[-1]["narration"].rstrip() + " Follow for more."
    yt = sc.get("youtube") or {}
    title = _clip(yt.get("title") or sc.get("topic", "Explained"), 95)
    if "#shorts" not in title.lower():
        title = title[:86] + " #shorts"
    return {"topic": sc.get("topic", ""), "hook": hook, "scenes": clean, "format": sig,
            "youtube": {"title": title, "description": str(yt.get("description", ""))[:4500],
                        "tags": [str(t)[:30] for t in (yt.get("tags") or [])][:10]},
            "instagram_caption": str(sc.get("instagram_caption", ""))[:2100]}


def review(sc):
    lines = []
    for i, st in enumerate(sc["scenes"]):
        shown = "; ".join(" / ".join(x for x in (it.get("label"), it.get("value", ""), it.get("sub"),
                                                    it.get("left", ""), it.get("right", "")) if x) for it in st["items"])
        if st["layout"] == "code":
            shown += " | code: " + " ; ".join(st["items"][0].get("lines", []))
        lines.append(f"{i + 1}. [{st['layout']}] {st.get('title') or st.get('hook')}: {st['narration']}  (on screen: {shown})")
    data = json.loads(llm(REVIEW.format(topic=sc["topic"], script="\n".join(lines)), label="quality gate review"))
    return {"score": int(data.get("score", 0)), "critical": [str(x) for x in data.get("critical_errors") or []],
            "minor": [str(x) for x in data.get("minor_issues") or []]}


def write_script(topic, used_formats=(), last_count=None, tries=6, seed=0):
    rng = random.Random(seed)
    formats = "\n".join(f"  {k:<11} {lo}-{hi} items - {desc}; item fields: {fields}" for k, (lo, hi, desc, fields) in SPEC.items())
    target = rng.choice([n for n in range(7, 11) if n != last_count])     # scene count also changes every video
    avoid = ""
    recent = list(used_formats)[-6:]
    if recent:
        avoid = ("- These format sequences were already used - do NOT reproduce any of them:\n" +
                 "\n".join(f"    {r}" for r in recent) + "\n")
    feedback, err, best = "", None, None
    for i in range(tries):
        prompt = PROMPT.format(topic=topic, formats=formats, icons=", ".join(ICONS), n_lo=target, n_hi=target,
                               min_distinct=6, avoid=avoid, feedback=feedback)
        try:
            sc = validate(json.loads(llm(prompt)), used_formats, last_count)
        except Exception as e:
            err = e
            print(f"  draft {i + 1} rejected: {e}")
            feedback = f"\nYour previous draft was rejected by the validator: {e}. Fix it.\n"
            continue
        try:
            rv = review(sc)
        except Exception as e:
            print(f"  quality gate unavailable ({e}) - accepting the validated draft")
            return sc
        print(f"  quality gate: score {rv['score']}/10, {len(rv['critical'])} real error(s)")
        sc["review"] = rv
        if not rv["critical"] and rv["score"] >= 7:
            return sc
        if not rv["critical"] and (best is None or rv["score"] > best["review"]["score"]):
            best = sc
        err = "; ".join(rv["critical"] + rv["minor"])[:500]
        feedback = "\nA senior reviewer REJECTED the previous draft. Fix every point:\n- " + "\n- ".join(rv["critical"] + rv["minor"]) + "\n"
    if best:
        return best
    raise RuntimeError(f"No usable script: {err}")
