"""
Composed scripts (no templates): the LLM designs every scene's 3D visual from building blocks - element types,
a 3D layout, per-element entrance + idle animations, links, camera move and scene transition - and the validator
refuses any scene composition the channel has ever used before (permanent signature log in state.json).
"""
import json
import random
import re

from writer import OBJECTS, REPAIR, _clip, _cue_ok, _unwrap, llm, review

C_TYPES = ["object", "box", "sphere", "cylinder", "cone", "torus", "prism", "panel", "ring", "helix", "wave", "surface",
           "particles", "link", "beam", "bars", "donut", "line", "matrix", "network", "gauge", "counter", "text", "orbit",
           "stack", "tunnel", "code", "stream", "burst"]
C_LAYOUTS = ["radial", "ring", "grid", "row", "stack", "timeline", "spiral", "tree", "cluster", "depth", "pyramid",
             "sphere", "diagonal", "wave", "scatter"]
C_APPEAR = ["grow", "pop", "fly", "drop", "rise", "unfold", "draw", "assemble", "glitch", "scan"]
C_IDLE = ["spin", "pulse", "orbit", "float", "none"]
C_TRANS = ["cut", "flash", "zoom", "whip", "fade", "glitch", "iris", "morph"]
C_CAMS = ["fly", "orbit", "crane", "dolly", "low", "top", "dutch", "spiral", "whip", "push"]
C_TONES = ["holo", "alt", "accent", "ink", "ember"]

PROMPT = """You are the director of "DataVelvet", a premium 3D motion-graphics explainer channel (vertical Shorts/Reels).
There are NO templates: you DESIGN every scene's visual yourself from 3D hologram building blocks, so that each scene
is a fresh, original visual metaphor for exactly what is being said.

Topic: "{topic}"
{facts}
BUILDING BLOCKS for "elements" (each appears exactly when its cue word is spoken):
  type: object (a hologram model; set "object": one of {objects}), box, sphere, cylinder, cone, torus, prism,
        panel (a floating screen), ring, helix, wave (oscillating signal), surface (moving 3D terrain), particles (a swarm;
        "count" 40-200), link (glowing arc with packets between two elements: "from" and "to" are element indexes),
        beam (straight laser between "from" and "to"), bars ("values": 2-8 numbers), donut ("values": shares), line
        ("values": a trend), matrix (grid of cells lighting up; "count" 3-7), network (node graph; "count" 5-14),
        gauge ("value" like "73%"), counter (a big number that counts up; "value"), text (a big word: "label"),
        orbit (satellites circling), stack (layers; "count" 2-5), tunnel (rings rushing into depth),
        code (a terminal / code panel; "lines": 2-5 real commands or code lines, max 34 chars each),
        stream (a river of particles flowing from element "from" to element "to"), burst (particles exploding outward)
  anim (entrance): grow, pop, fly, drop, rise, unfold, draw, assemble, glitch, scan
  idle (after it appears): spin, pulse, orbit, float, none
  tone: holo, alt, accent, ink, ember          size: 0.6-1.8
  label (max 20 chars, shown as a callout), sub (max 28 chars), cue (1-3 words copied EXACTLY from this scene's lines)
SCENE fields: "layout" (how elements are arranged in 3D): {layouts}
              "camera" (move): {cams}       "transition" (how the scene enters): {trans}

RULES
- {n} scenes. Scene 1 is the hook (its lines are a curiosity headline shown huge). The last scene's lines end with
  "Follow for more."
- Every scene: "title" (max 26 chars), "lines" (1-2 short spoken sentences, max 32 words), "visual" {{"layout", "camera",
  "transition", "elements": [2-7 elements]}}. Use at least 2 different element types per scene.
- Across the video use at least 9 different element types, never the same layout twice, never the same camera twice in
  a row, and vary entrances, idles and transitions. Invent visual METAPHORS (e.g. a request = a particle swarm flying
  through a tunnel; a bottleneck = a narrowing cone; consensus = a network lighting up) - not boring boxes.
- Every element needs a cue (exact words from that scene's lines, in speaking order). Links/beams/streams need from/to.
- The first element of scene 1 must appear on its FIRST spoken word: motion from the very first second.
- Each scene lists 1-3 "emphasis" words (exact words from its lines) that punch out of the captions.
- Optionally ONE middle scene is a quiz: "quiz": {{"question": max 50 chars, "options": [2-3 short answers], "answer":
  index of the right option, "cue": the word where the answer is revealed}}. Its lines ask, pause, then reveal.
- LEVEL: {level}.{series}
- Give "titles": 3 different YouTube title options (max 60 chars each, curiosity-driven, no hashtags).
- Total narration 140-200 words. Accurate, specific facts and real numbers only. Casual, clear, no emojis/markdown.
{avoid}- "youtube": {{"title": max 70 chars ending " #shorts", "description": 2 sentences + 5 hashtags, "tags": 6-8}},
  "instagram_caption": 2-3 short lines + "Save this for later." + 6-8 hashtags.
Return ONLY JSON: {{"topic", "titles": [3], "scenes": [{{"title", "lines": [...], "emphasis": [...], "quiz"?: {{...}}, "visual": {{...}}}}],
"youtube", "instagram_caption"}}
{feedback}"""


def signature(v):
    return v["layout"] + "|" + ",".join(sorted(f"{e['type']}:{e['anim']}" for e in v["elements"]))


def validate(sc, banned=()):
    sc = _unwrap(sc)
    scenes = sc.get("scenes") or []
    if not 6 <= len(scenes) <= 10:
        raise ValueError(f"need 6-10 scenes, got {len(scenes)}")
    clean, bad, total, layouts, types_all, sigs = [], 0, 0, [], set(), []
    for i, s in enumerate(scenes):
        src = s.get("lines") or s.get("narration") or s.get("voiceover") or s.get("text") or s.get("script") or []
        if isinstance(src, str):                     # some models return one string instead of a list
            src = re.split(r"(?<=[.!?])\s+", src.strip())
        lines = [re.sub(r"\s+", " ", str(x)).strip().replace("**", "") for x in src if str(x).strip()]
        lines = [x for x in lines if len(x.split()) >= 2][:3]
        if not lines:
            raise ValueError(f"scene {i + 1} has no lines")
        if i == len(scenes) - 1 and not re.search(r"follow for more", " ".join(lines), re.I):
            lines[-1] = lines[-1].rstrip() + " Follow for more."
        text = " ".join(lines)
        if len(text.split()) > 40:
            raise ValueError(f"scene {i + 1} is too long ({len(text.split())} words, max 32)")
        v = s.get("visual") or s.get("data") or {}
        raw = [e for e in (v.get("elements") or []) if isinstance(e, dict)][:7]
        if len(raw) < 2:
            raise ValueError(f"scene {i + 1} needs 2-7 elements, got {len(raw)}")
        els = []
        for k, e in enumerate(raw):
            total += 1
            cue = str(e.get("cue") or "")
            if not (cue and _cue_ok(cue, text)):
                bad += 1
                cue = ""
            t = e.get("type") if e.get("type") in C_TYPES else "sphere"
            try:
                size = max(0.6, min(1.8, float(e.get("size") or 1)))
            except (TypeError, ValueError):
                size = 1.0
            o = {"type": t, "label": _clip(e.get("label"), 20), "sub": _clip(e.get("sub"), 28), "cue": cue,
                 "anim": e.get("anim") if e.get("anim") in C_APPEAR else random.choice(C_APPEAR),
                 "idle": e.get("idle") if e.get("idle") in C_IDLE else random.choice(C_IDLE),
                 "tone": e.get("tone") if e.get("tone") in C_TONES else random.choice(C_TONES), "size": size}
            if t == "object":
                o["object"] = e.get("object") if e.get("object") in OBJECTS else random.choice(OBJECTS)
            if t in ("bars", "donut", "line"):
                o["values"] = [float(x) for x in (e.get("values") or []) if isinstance(x, (int, float))][:8]
            if t in ("gauge", "counter"):
                o["value"] = _clip(e.get("value"), 12)
                if not re.search(r"\d", o["value"]):
                    raise ValueError(f"scene {i + 1}: {t} needs a numeric value")
            if t in ("particles", "matrix", "network", "stack"):
                try:
                    o["count"] = int(e.get("count") or 0)
                except (TypeError, ValueError):
                    o["count"] = 0
            if t in ("link", "beam"):
                for f in ("from", "to"):
                    if isinstance(e.get(f), int) and 0 <= e[f] < len(raw) and e[f] != k:
                        o[f] = e[f]
            if t == "code":
                o["lines"] = [str(x)[:34] for x in (e.get("lines") or []) if str(x).strip()][:5] or [o["label"] or "$ run"]
            if t == "stream":
                for f in ("from", "to"):
                    if isinstance(e.get(f), int) and 0 <= e[f] < len(raw) and e[f] != k:
                        o[f] = e[f]
                o["count"] = 60
            if t == "text" and not o["label"]:
                raise ValueError(f"scene {i + 1}: text element needs a label")
            types_all.add(t)
            els.append(o)
        if len({e["type"] for e in els}) < 2:
            raise ValueError(f"scene {i + 1} uses one element type - use at least 2")
        lay = v.get("layout")
        if lay not in C_LAYOUTS or lay in layouts:   # unknown or repeated layout: repair instead of rejecting the draft
            lay = random.choice([x for x in C_LAYOUTS if x not in layouts] or C_LAYOUTS)
        layouts.append(lay)
        vis = {"layout": lay, "elements": els,
               "camera": v.get("camera") if v.get("camera") in C_CAMS else random.choice(C_CAMS),
               "transition": v.get("transition") if v.get("transition") in C_TRANS else random.choice(C_TRANS)}
        if i == 0:
            vis["hook"] = True
        if i == len(scenes) - 1:
            vis["cta"] = True
        emph = [str(w) for w in (s.get("emphasis") or []) if isinstance(w, str) and _cue_ok(w, text)][:3]
        if emph:
            vis["emphasis"] = emph
        q = s.get("quiz") if isinstance(s.get("quiz"), dict) else None
        if q and 0 < i < len(scenes) - 1 and isinstance(q.get("options"), list) and 2 <= len(q["options"]) <= 3:
            try:
                ans = int(q.get("answer", 0))
            except (TypeError, ValueError):
                ans = -1
            if 0 <= ans < len(q["options"]):
                vis["quiz"] = {"question": _clip(q.get("question"), 50), "options": [_clip(o, 22) for o in q["options"]], "answer": ans,
                               "cue": str(q.get("cue")) if q.get("cue") and _cue_ok(str(q.get("cue")), text) else ""}
        sig = signature(vis)
        tries = 0
        while (sig in banned or sig in sigs) and tries < 40:   # never reuse a composition: re-roll entrances until unique
            e = random.choice(els)
            e["anim"] = random.choice([a for a in C_APPEAR if a != e["anim"]])
            sig, tries = signature(vis), tries + 1
        if sig in banned or sig in sigs:
            raise ValueError(f"scene {i + 1} repeats a composition used before ({sig}) - design a new one")
        sigs.append(sig)
        clean.append({"plate": "compose", "title": _clip(s.get("title"), 28), "lines": lines, "data": vis})
    if len(types_all) < 7:
        raise ValueError(f"only {len(types_all)} element types in the whole video - use at least 9")
    for j in range(1, len(clean)):
        if clean[j]["data"]["camera"] == clean[j - 1]["data"]["camera"]:
            clean[j]["data"]["camera"] = random.choice([c for c in C_CAMS if c != clean[j - 1]["data"]["camera"]])
    if bad > max(4, total * 0.3):
        raise ValueError(f"{bad} of {total} cues are not exact words from their scene's lines")
    words = sum(len(" ".join(s["lines"]).split()) for s in clean)
    if not 120 <= words <= 230:
        raise ValueError(f"narration length {words} words (need 140-200)")
    yt = sc.get("youtube") or {}
    opts = [str(t).strip() for t in (sc.get("titles") or []) if str(t).strip()][:3]
    title = _clip(best_title(opts) if opts else (yt.get("title") or sc.get("topic", "Explained")), 95)
    if "#shorts" not in title.lower():
        title = title[:86] + " #shorts"
    return {"topic": sc.get("topic", ""), "scenes": clean, "format": " > ".join(layouts), "signatures": sigs,
            "youtube": {"title": title, "description": str(yt.get("description", ""))[:4500],
                        "tags": [str(t)[:30] for t in (yt.get("tags") or [])][:10]},
            "instagram_caption": str(sc.get("instagram_caption", ""))[:2100]}


LANG_VOICES = {"es": "es-ES-AlvaroNeural", "pt": "pt-BR-AntonioNeural", "fr": "fr-FR-HenriNeural", "de": "de-DE-ConradNeural",
               "it": "it-IT-DiegoNeural"}
TRANSLATE = """Translate this short explainer video script into {lang}. Keep the EXACT same JSON structure and every non-text
field. Translate: "title", every "lines" sentence, "emphasis" words, element "label" / "sub", quiz "question" / "options",
"youtube" title + description, "instagram_caption". Every "cue" (and quiz "cue", "emphasis") must be 1-3 words copied
EXACTLY from the translated lines of its scene. Keep labels short (max 20 chars). The last scene must end with the
{lang} equivalent of "Follow for more." Return ONLY the JSON.

{script}"""


def translate(sc, lang):
    """Same video in another language: translated narration, captions, labels and cues; same visuals and style."""
    body = {"topic": sc["topic"], "scenes": [{"title": s["title"], "lines": s["lines"], "emphasis": s["data"].get("emphasis", []),
                                              "quiz": s["data"].get("quiz"), "visual": s["data"]} for s in sc["scenes"]],
            "youtube": sc["youtube"], "instagram_caption": sc["instagram_caption"]}
    raw = _unwrap(json.loads(llm(TRANSLATE.format(lang=lang, script=json.dumps(body, ensure_ascii=False)), label=f"translation ({lang})")))
    out = dict(sc)
    out["scenes"] = []
    for s0, s1 in zip(sc["scenes"], raw.get("scenes") or []):
        d = json.loads(json.dumps(s0["data"]))
        v = s1.get("visual") or {}
        for e0, e1 in zip(d.get("elements", []), v.get("elements") or []):
            for f in ("label", "sub", "cue"):
                if e1.get(f):
                    e0[f] = _clip(e1[f], 28)
            if e1.get("lines"):
                e0["lines"] = e1["lines"][:5]
        if s1.get("emphasis"):
            d["emphasis"] = s1["emphasis"][:3]
        if d.get("quiz") and isinstance(s1.get("quiz"), dict):
            d["quiz"].update({k: s1["quiz"][k] for k in ("question", "options", "cue") if s1["quiz"].get(k)})
        lines = [str(x) for x in (s1.get("lines") or s0["lines"])][:3]
        out["scenes"].append({"plate": s0["plate"], "title": _clip(s1.get("title") or s0["title"], 28), "lines": lines, "data": d})
    if len(out["scenes"]) != len(sc["scenes"]):
        raise ValueError("translation lost scenes")
    out["youtube"] = {**sc["youtube"], **(raw.get("youtube") or {})}
    out["instagram_caption"] = str(raw.get("instagram_caption") or sc["instagram_caption"])
    out["lang"] = lang
    return out


def best_title(opts):
    """Pick the strongest of the AI's title options (numbers, curiosity, Shorts-friendly length)."""
    def score(t):
        s = 0
        s += 2 if re.search(r"\d", t) else 0
        s += 2 if 30 <= len(t) <= 60 else 0
        s += 1 if re.search(r"\b(why|how|secret|actually|really|never|nobody|inside)\b", t, re.I) else 0
        s += 1 if "?" in t else 0
        s -= 2 if sum(c.isupper() for c in t) > len(t) * 0.5 else 0
        return s
    return max(opts, key=score)


def write(topic, banned=(), recent=(), angle=None, tries=6, seed=0, facts=None, hints="", level="engineer", series=None):
    rng = random.Random(seed)
    n = rng.choice([7, 8, 8, 9])
    avoid = hints or ""
    if angle:
        avoid += f"- STORY ANGLE ({angle[0]}): {angle[1]} Explain it in a way this channel has not used before.\n"
    if recent:
        avoid += ("- Recent videos used these layout sequences - build something structurally different:\n"
                  + "\n".join(f"    {r}" for r in list(recent)[-5:]) + "\n")
    banned = set(banned)
    facts_txt = (f"\nREFERENCE FACTS (from {', '.join(facts['sources'][:3])}) - use their numbers; never contradict them:\n"
                 f"{facts['facts'][:3500]}\n") if facts and facts.get("facts") else ""
    series_txt = ""
    if series and series.get("name"):
        series_txt = f' This is episode {series.get("ep", 1)} of the series "{series["name"]}".'
        if series.get("next"):
            series_txt += f' End the last scene by teasing the next episode: "{series["next"]}" (one short line before "Follow for more.").'
    fmt = dict(topic=topic, objects="|".join(OBJECTS), layouts=", ".join(C_LAYOUTS), cams=", ".join(C_CAMS),
               trans=", ".join(C_TRANS), n=n, avoid=avoid, facts=facts_txt, level=level, series=series_txt)
    feedback, err, cands = "", None, []
    for i in range(tries):
        try:
            sc = validate(json.loads(llm(PROMPT.format(**fmt, feedback=feedback), label="composed script")), banned)
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
    for sc in sorted(cands, key=lambda c: (c["review"]["score"], -len(c["review"]["critical"])), reverse=True)[:2]:
        rv = sc["review"]
        if rv["score"] < 7:
            continue
        try:
            body = {"topic": sc["topic"], "scenes": [{"title": s["title"], "lines": s["lines"], "visual": s["data"]} for s in sc["scenes"]],
                    "youtube": sc["youtube"], "instagram_caption": sc["instagram_caption"]}
            fixed = json.loads(llm(REPAIR.format(script=json.dumps(body, ensure_ascii=False),
                                                  errors="\n- ".join(rv["critical"] + rv["minor"])), label="repair"))
            out = validate(fixed, banned)
            out["topic"] = out.get("topic") or topic
            out["review"] = {**rv, "repaired": True}
            print(f"  repaired the best draft ({rv['score']}/10) using the reviewer's corrections")
            return out
        except Exception as e:
            print(f"  repair failed: {e}")
    raise RuntimeError(f"No usable composed script: {err}")
