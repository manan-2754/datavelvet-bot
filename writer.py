"""
Script writer for the Motion-as-Code bot: an LLM (Gemini -> OpenRouter -> Groq -> OpenCode -> Gemini Lite) writes a
short explainer as a sequence of plates (2D: hook, title, specimen, flows, form, stats, compare, outro; 3D holo: holo,
scene3d, layers, orbit, tunnel, bars3d), each
scene with its spoken lines and the data its plate draws. A validator enforces the plate schemas and exact cue
words; a second model pass fact-checks it.
"""
import json
import os
import random
import re
import time

import requests

MODELS = ["gemini-3.5-flash", "gemini-3.8-flash", "gemini-flash-latest"]
LITE_MODELS = ["gemini-3.1-flash-lite", "gemini-flash-lite-latest"]
FALLBACKS = [
    ("OpenRouter", "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY",
     ["nvidia/nemotron-3-ultra-550b-a55b:free", "nvidia/nemotron-3-super-120b-a12b:free", "nvidia/nemotron-3.5-lightning:free"]),
    ("Groq", "https://api.groq.com/openai/v1", "GROQ_API_KEY", ["openai/gpt-oss-120b", "qwen/qwen3.8-27b"]),
    ("OpenCode", "https://opencode.ai/zen/v1", "OPENCODE_API_KEY", ["gemini-3.8-flash", "claude-sonnet-5-5", "gpt-5.4-mini"]),
]
MIDDLE = ["title", "specimen", "holo", "flows", "form", "stats", "compare", "scene3d", "layers", "orbit", "tunnel", "bars3d"]
HOLO3D = {"holo", "scene3d", "layers", "orbit", "tunnel", "bars3d"}
OBJECTS = ["server", "db", "globe", "cube", "pyramid", "chip", "router", "cloud", "lock", "gear", "user", "phone",
           "laptop", "stack", "shield", "helix", "bot"]
OBJ_TXT = "|".join(OBJECTS)

PLATES = """
PLATES (each scene picks one; the visuals are drawn from "data" exactly when the cue words are spoken).
2D plates (hand-plotted paper / graph style):
- "hook" (FIRST scene only): giant karaoke headline of the lines + one motif.
    data: {"motif": "dial"|"chart"|"number"|"strike"|"holo", "value": short text (for number: a striking figure like "100,000" or "0.2 ms"; for strike: what gets crossed out, max 22 chars), "object": for holo, one of OBJ, "label": max 30 chars caption, "cue": 1-3 words}
- "title": the pen writes a key term huge, then 2-3 stacked process boxes.
    data: {"term": max 14 chars (one key word or acronym), "termCue": words, "note": max 44 chars, "items": [{"label": max 24 chars, "sub": max 56 chars, "cue": words}] x2-3}
- "specimen": a paper specimen sheet: a helix spine with 2-4 property cards and a rubber stamp.
    data: {"items": [{"label": max 20 chars, "sub": max 70 chars, "cue": words}] x2-4, "stamp": max 20 chars verdict, "stampCue": words}
- "flows": a hub with 2-4 connected nodes, packets streaming, live counters ticking.
    data: {"hub": {"label": max 12 chars, "unit": short unit, "cue": words}, "items": [{"label": max 12 chars, "unit": short unit like "req/s", "value": number per second, "cue": words}] x2-4, "packetsCue": words, "countersCue": words}
- "form": a paper process form: 3-5 numbered steps typed in, then a stamp.
    data: {"form": like "FORM 4-C", "items": [{"label": max 26 chars, "sub": max 40 chars, "cue": words}] x3-5, "stamp": max 18 chars, "stampCue": words}
- "stats": 2-3 cards slam in with big numbers counting up, plus a total line.
    data: {"items": [{"value": number with unit, max 9 chars, e.g. "99.99%", "3 ms", "1,000,000", "label": max 30 chars, "cue": words}] x2-3, "total": max 32 chars, "totalCue": words}
- "compare": A vs B headers and 2-4 typed rows.
    data: {"left": max 12 chars, "right": max 12 chars, "rows": [{"label": max 22 chars, "left": max 16 chars, "right": max 16 chars, "cue": words}] x2-4}
3D HOLO plates (glowing hologram wireframes; a moving 3D camera flies, orbits and cranes around them):
- "holo": showcase - 1-3 big hologram objects printed on pedestals, the camera circling them.
    data: {"items": [{"label": max 18 chars, "object": one of OBJ, "sub": max 28 chars, "cue": words}] x1-3}
- "scene3d": a 3D diorama - 2-4 hologram objects on a floor joined by glowing 3D links with packets flying between them.
    data: {"items": [{"label": max 18 chars, "object": one of OBJ, "sub": max 28 chars, "cue": words}] x2-4, "link": "chain"|"hub"|"ring", "packetsCue": words}
- "layers": an exploded 3D architecture stack - 3-5 floating layers (top to bottom) slide in, data falls through them.
    data: {"items": [{"label": max 20 chars, "sub": max 28 chars, "object": optional one of OBJ, "cue": words}] x3-5}
- "orbit": a core object with 2-5 satellites orbiting on tilted rings, tethered by data streams.
    data: {"core": {"label": max 16 chars, "object": one of OBJ, "cue": words}, "items": [{"label": max 16 chars, "object": one of OBJ, "cue": words}] x2-5}
- "tunnel": the camera flies a data packet through 3-5 glowing gates (a pipeline / journey / request path, in order).
    data: {"items": [{"label": max 20 chars, "sub": max 28 chars, "cue": words}] x3-5}
- "bars3d": a holographic 3D bar chart - 2-5 bars grow with their numbers counting up.
    data: {"items": [{"value": number with unit, max 9 chars, "label": max 22 chars, "cue": words}] x2-5, "total": optional max 32 chars, "totalCue": words}
- "outro" (LAST scene only): big closing line; its lines end with "Follow for more."
    data: {}
""".replace("OBJ", OBJ_TXT)

PROMPT = """You write scripts for "DataVelvet", a premium motion-graphics explainer channel (YouTube Shorts + Instagram
Reels, vertical). Each video is a sequence of animated plates in a hand-plotted engineering style.

Topic: "{topic}"
{plates}
RULES
- {n} scenes: scene 1 is "hook", the last is "outro", the middle scenes each use a DIFFERENT plate (never repeat one).
  Choose the plate that best SHOWS what that scene explains (numbers -> stats or bars3d, a process -> form, title or
  tunnel, components talking -> flows or scene3d, architecture tiers -> layers, one thing with parts around it -> orbit,
  physical things -> holo, two options -> compare, properties -> specimen).
- AT LEAST 3 middle scenes must be 3D HOLO plates (holo, scene3d, layers, orbit, tunnel, bars3d) and at least 1 must be
  a 2D plate; alternate them. Pick hologram objects that fit what is said.
{avoid}- Each scene: "plate", "title" (max 26 chars; a punchy header), "lines" (1-2 short spoken sentences, max 32 words
  total), "data" as specified. EVERY cue is 1-3 words copied EXACTLY from that scene's own lines, in the order they
  are spoken, at the moment that thing should appear.
- Total narration 140-200 words. Hook = a curiosity line that makes people stay. Accurate, specific facts and real
  numbers only. Casual, clear, no emojis, no markdown in lines.
- "youtube": {{"title": max 70 chars ending " #shorts", "description": 2 sentences + 5 hashtags, "tags": 6-8 strings}},
  "instagram_caption": 2-3 short lines + "Save this for later." + 6-8 hashtags.

Return ONLY JSON: {{"topic", "scenes": [{{"plate", "title", "lines": [...], "data": {{...}}}}], "youtube", "instagram_caption"}}
{feedback}"""

REVIEW = """You are a senior engineer and teacher reviewing a short explainer script before it is published.
Topic: "{topic}"

SCRIPT:
{script}

Check: (1) any statement, number or label that is technically WRONG, (2) is it clear for a curious beginner.
Simplifications are fine. Return ONLY JSON:
{{"score": 1-10, "critical_errors": ["what is wrong + correct fact", ...], "minor_issues": ["...", ...]}}"""


REPAIR = """Here is a short explainer script (JSON) and a senior reviewer's corrections. Return the SAME JSON structure
with every correction applied: fix wrong facts, numbers and labels in "lines" AND in "data". Keep the plates, keep
every cue as 1-3 words copied exactly from that scene's lines (update cues if you change the words), keep it short.

CORRECTIONS:
- {errors}

SCRIPT:
{script}

Return ONLY the corrected JSON."""


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


CLAUDE_MODEL = "claude-haiku-5-5"   # paid backup: cheap, reliable at long structured briefs


def _claude_call(prompt, model=CLAUDE_MODEL):
    """Claude via the official Anthropic SDK (reads ANTHROPIC_API_KEY)."""
    import anthropic
    client = anthropic.Anthropic(timeout=300.0, max_retries=2)
    r = client.messages.create(model=model, max_tokens=16000, output_config={"effort": "medium"},
                               messages=[{"role": "user", "content": prompt}])
    if r.stop_reason == "refusal":
        raise RuntimeError(f"refused ({getattr(r.stop_details, 'category', None)})")
    if r.stop_reason == "max_tokens":
        raise RuntimeError("response cut off at max_tokens")
    text = "".join(b.text for b in r.content if b.type == "text")
    json.loads(_json_text(text))
    return text


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
    """Gemini first; then Claude Haiku (paid backup); then OpenRouter -> Groq -> OpenCode; Gemini Lite last."""
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
    if os.getenv("ANTHROPIC_API_KEY", "").strip():
        for attempt in range(2):
            try:
                text = _claude_call(prompt)
                print(f"  {label} by Claude / {CLAUDE_MODEL}")
                return _json_text(text)
            except Exception as e:
                last = f"Claude/{CLAUDE_MODEL}: {e}"
                print(f"  {last}")
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
    return re.sub(r"[^a-z0-9()]", "", w.lower())


def _cue_ok(cue, text):
    toks = [_norm(w) for w in str(cue).split() if _norm(w)]
    ws = [_norm(w) for w in text.split() if _norm(w)]
    return bool(toks) and any(ws[i:i + len(toks)] == toks for i in range(len(ws) - len(toks) + 1))


def _clip(s, n):
    s = re.sub(r"\s+", " ", str(s or "")).strip().replace("**", "")
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


def format_signature(scenes):
    return "|".join(f"{s['plate']}:{len(s['data'].get('items') or s['data'].get('rows') or [])}" for s in scenes)


def _unwrap(sc):
    """Some models wrap the script ({"script": {...}}) - find the dict that holds the scenes."""
    if isinstance(sc, dict) and "scenes" in sc:
        return sc
    if isinstance(sc, dict):
        for v in sc.values():
            if isinstance(v, dict) and "scenes" in v:
                return v
    if isinstance(sc, list):
        return {"scenes": sc}
    return sc if isinstance(sc, dict) else {}


def validate(sc, used_formats=()):
    sc = _unwrap(sc)
    scenes = sc.get("scenes") or []
    if len(scenes) < 6:
        raise ValueError(f"need at least 6 scenes, got {len(scenes)}")
    if scenes[0].get("plate") != "hook" or scenes[-1].get("plate") != "outro":
        raise ValueError("first scene must be 'hook' and the last 'outro'")
    seen, clean = set(), []
    stats = {"bad": 0, "total": 0}
    for i, s in enumerate(scenes):
        plate = s.get("plate")
        if i not in (0, len(scenes) - 1):
            if plate not in MIDDLE:
                raise ValueError(f"unknown plate {plate!r}")
            if plate in seen:
                raise ValueError(f"plate {plate!r} used twice - every middle scene needs a different plate")
            seen.add(plate)
        lines = [re.sub(r"\s+", " ", str(x)).strip().replace("**", "") for x in (s.get("lines") or []) if str(x).strip()]
        lines = [x for x in lines if len(x.split()) >= 2][:3]
        if not lines:
            raise ValueError(f"scene {i + 1} has no lines")
        text = " ".join(lines)
        if len(text.split()) > 40:
            raise ValueError(f"scene {i + 1} is too long ({len(text.split())} words, max 32)")
        d = s.get("data") if isinstance(s.get("data"), dict) else {}

        def cue(v, text=text):
            stats["total"] += 1
            if v and _cue_ok(v, text):
                return str(v)
            stats["bad"] += 1
            return ""
        out = {}
        if plate == "hook":
            out = {"motif": d.get("motif") if d.get("motif") in ("dial", "chart", "number", "strike", "holo") else "number",
                   "value": _clip(d.get("value"), 22), "label": _clip(d.get("label"), 30), "cue": cue(d.get("cue"))}
            if out["motif"] == "holo":
                out["object"] = d.get("object") if d.get("object") in OBJECTS else random.choice(OBJECTS)
        elif plate == "outro":
            if not re.search(r"follow for more", text, re.I):
                lines[-1] = lines[-1].rstrip() + " Follow for more."
        else:
            lim = {"title": (2, 3), "specimen": (2, 4), "holo": (1, 3), "flows": (2, 4), "form": (3, 5), "stats": (2, 3), "compare": (2, 4),
                   "scene3d": (2, 4), "layers": (3, 5), "orbit": (2, 5), "tunnel": (3, 5), "bars3d": (2, 5)}[plate]
            raw = d.get("rows") if plate == "compare" else d.get("items")
            raw = [x for x in (raw or []) if isinstance(x, dict)][:lim[1]]
            if len(raw) < lim[0]:
                raise ValueError(f"{plate} scene needs {lim[0]}-{lim[1]} items, got {len(raw)}")
            its = []
            for it in raw:
                o = {"label": _clip(it.get("label"), 26), "sub": _clip(it.get("sub"), 70), "cue": cue(it.get("cue"))}
                if plate in ("holo", "scene3d", "orbit") or (plate == "layers" and it.get("object")):
                    o["object"] = it.get("object") if it.get("object") in OBJECTS else random.choice(OBJECTS)
                if plate in ("flows", "stats", "bars3d"):
                    o["value"] = _clip(it.get("value"), 12)
                    o["unit"] = _clip(it.get("unit"), 10)
                if plate in ("stats", "bars3d") and not re.search(r"\d", o["value"]):
                    raise ValueError(f"every {plate} value must contain a number")
                if plate == "compare":
                    o["left"], o["right"] = _clip(it.get("left"), 16), _clip(it.get("right"), 16)
                    if not o["left"] or not o["right"]:
                        raise ValueError("compare rows need left and right")
                its.append(o)
            out["rows" if plate == "compare" else "items"] = its
            if plate == "title":
                out.update(term=_clip(d.get("term"), 14).upper(), termCue=cue(d.get("termCue")), note=_clip(d.get("note"), 44))
                if not out["term"]:
                    raise ValueError("title scene needs a term")
            elif plate in ("specimen", "form"):
                out.update(stamp=_clip(d.get("stamp"), 20), stampCue=cue(d.get("stampCue")))
                if plate == "form":
                    out["form"] = _clip(d.get("form"), 12)
            elif plate == "flows":
                h = d.get("hub") if isinstance(d.get("hub"), dict) else {}
                out.update(hub={"label": _clip(h.get("label"), 12) or "SYSTEM", "unit": _clip(h.get("unit"), 10), "cue": cue(h.get("cue")),
                                "value": _clip(h.get("value"), 12)},
                           packetsCue=cue(d.get("packetsCue")), countersCue=cue(d.get("countersCue")))
            elif plate in ("stats", "bars3d"):
                if plate == "stats" or d.get("total"):
                    out.update(total=_clip(d.get("total"), 32), totalCue=cue(d.get("totalCue")))
            elif plate == "scene3d":
                out.update(link=d.get("link") if d.get("link") in ("chain", "hub", "ring") else random.choice(["chain", "hub", "ring"]),
                           packetsCue=cue(d.get("packetsCue")))
            elif plate == "orbit":
                c = d.get("core") if isinstance(d.get("core"), dict) else {}
                out["core"] = {"label": _clip(c.get("label"), 16) or "CORE", "cue": cue(c.get("cue")),
                               "object": c.get("object") if c.get("object") in OBJECTS else random.choice(OBJECTS)}
            elif plate == "compare":
                out.update(left=_clip(d.get("left"), 12) or "A", right=_clip(d.get("right"), 12) or "B")
        clean.append({"plate": plate, "title": _clip(s.get("title"), 28), "lines": lines, "data": out})
    if len(seen) < 4:
        raise ValueError(f"only {len(seen)} different middle plates - use at least 4")
    n3 = len(seen & HOLO3D)
    if n3 < 2 or n3 == len(seen):
        raise ValueError(f"{n3} 3D holo plates among {len(seen)} middle scenes - use at least 3 3D plates and at least one 2D plate")
    if stats["bad"] > max(3, stats["total"] * 0.3):
        raise ValueError(f"{stats['bad']} of {stats['total']} cues are not exact words from their scene's lines")
    words = sum(len(" ".join(s["lines"]).split()) for s in clean)
    if not 120 <= words <= 230:
        raise ValueError(f"narration length {words} words (need 140-200)")
    sig = format_signature(clean)
    if sig in set(used_formats):
        raise ValueError("this exact plate sequence was used before - choose a different order or plates")
    yt = sc.get("youtube") or {}
    title = _clip(yt.get("title") or sc.get("topic", "Explained"), 95)
    if "#shorts" not in title.lower():
        title = title[:86] + " #shorts"
    return {"topic": sc.get("topic", ""), "scenes": clean, "format": sig,
            "youtube": {"title": title, "description": str(yt.get("description", ""))[:4500],
                        "tags": [str(t)[:30] for t in (yt.get("tags") or [])][:10]},
            "instagram_caption": str(sc.get("instagram_caption", ""))[:2100]}


def review(sc):
    rows = []
    for i, s in enumerate(sc["scenes"]):
        shown = json.dumps(s["data"], ensure_ascii=False)[:400]
        rows.append(f"{i + 1}. [{s['plate']}] {s['title']}: {' '.join(s['lines'])}  (on screen: {shown})")
    data = json.loads(llm(REVIEW.format(topic=sc["topic"], script="\n".join(rows)), label="quality gate review"))
    return {"score": int(data.get("score", 0)), "critical": [str(x) for x in data.get("critical_errors") or []],
            "minor": [str(x) for x in data.get("minor_issues") or []]}


def write_script(topic, used_formats=(), tries=6, seed=0, angle=None, hook=None):
    rng = random.Random(seed)
    n = rng.choice([7, 8, 8, 9])
    recent = list(used_formats)[-8:]
    avoid = ("- These plate sequences were used recently - do NOT reproduce any of them:\n" +
             "\n".join(f"    {r}" for r in recent) + "\n") if recent else ""
    if angle:
        avoid += f"- STORY ANGLE for this video ({angle[0]}): {angle[1]} Explain it in a way this channel has not used before." + chr(10)
    if hook:
        avoid += f'- The hook scene must use motif "{hook}".' + chr(10)
    feedback, err, cands = "", None, []
    for i in range(tries):
        prompt = PROMPT.format(topic=topic, plates=PLATES, n=n, avoid=avoid, feedback=feedback)
        try:
            sc = validate(json.loads(llm(prompt)), used_formats)
            sc["topic"] = sc.get("topic") or topic
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
        cands.append(sc)
        err = "; ".join(rv["critical"] + rv["minor"])[:500]
        feedback = "\nA senior reviewer REJECTED the previous draft. Fix every point:\n- " + "\n- ".join(rv["critical"] + rv["minor"]) + "\n"
    # nothing came back perfectly clean: repair the best draft with the reviewer's own corrections
    for sc in sorted(cands, key=lambda c: (c["review"]["score"], -len(c["review"]["critical"])), reverse=True)[:2]:
        rv = sc["review"]
        if rv["score"] < 7:
            continue
        try:
            body = {k: sc[k] for k in ("topic", "scenes", "youtube", "instagram_caption")}
            fixed = json.loads(llm(REPAIR.format(script=json.dumps(body, ensure_ascii=False),
                                                  errors="\n- ".join(rv["critical"] + rv["minor"])), label="repair"))
            out = validate(fixed, used_formats)
            out["topic"] = out.get("topic") or topic
            out["review"] = {**rv, "repaired": True}
            print(f"  repaired the best draft ({rv['score']}/10) using the reviewer's corrections")
            return out
        except Exception as e:
            print(f"  repair failed: {e}")
    raise RuntimeError(f"No usable script: {err}")


def prepare_edits(script):
    """Photo-tutorial videos: give every "edit" scene its photo + region metadata and the layer stack it starts
    from (simulating the previous scenes' actions), so each plate renders independently."""
    from pathlib import Path
    pool = {p["file"]: p for p in json.loads((Path(__file__).parent / "app" / "public" / "photos" / "pool.json").read_text(encoding="utf-8"))}
    photo = script.get("photo")
    meta = pool.get(photo, {})
    layers = []
    for sc in script["scenes"]:
        if sc["plate"] != "edit":
            continue
        d = sc.setdefault("data", {})
        d.update(photo=photo, sky=meta.get("sky", 0.3), subject=meta.get("subject", [0.5, 0.55, 0.2, 0.25]),
                 edits=json.loads(json.dumps(layers)))
        for a in d.get("acts", []):
            if a.get("do") == "slider":
                if a.get("new") or not layers:
                    layers.append({"kind": a.get("kind", "exposure"), "value": a.get("from", 0), "region": a.get("region", "all"), "mask": "full", "paint": 1})
                    a["layer"] = len(layers) - 1
                else:
                    a.setdefault("layer", len(layers) - 1)
                layers[a["layer"]]["value"] = a.get("to", 0)
            elif a.get("do") == "invert" and layers:
                a.setdefault("layer", len(layers) - 1)
                L = layers[a["layer"]]
                L["mask"] = "full" if L["mask"] == "none" else "none"
            elif a.get("do") == "paint" and layers:
                a.setdefault("layer", len(layers) - 1)
                layers[a["layer"]].update(mask="region", region=a.get("region", "sky"), paint=1)
    return script
