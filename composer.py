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
           "stack", "tunnel"]
C_LAYOUTS = ["radial", "ring", "grid", "row", "stack", "timeline", "spiral", "tree", "cluster", "depth", "pyramid",
             "sphere", "diagonal", "wave", "scatter"]
C_APPEAR = ["grow", "pop", "fly", "drop", "rise", "unfold", "draw", "assemble", "glitch", "scan"]
C_IDLE = ["spin", "pulse", "orbit", "float", "none"]
C_TRANS = ["cut", "flash", "zoom", "whip", "fade", "glitch", "iris"]
C_CAMS = ["fly", "orbit", "crane", "dolly", "low", "top", "dutch", "spiral", "whip", "push"]
C_TONES = ["holo", "alt", "accent", "ink", "ember"]

PROMPT = """You are the director of "DataVelvet", a premium 3D motion-graphics explainer channel (vertical Shorts/Reels).
There are NO templates: you DESIGN every scene's visual yourself from 3D hologram building blocks, so that each scene
is a fresh, original visual metaphor for exactly what is being said.

Topic: "{topic}"

BUILDING BLOCKS for "elements" (each appears exactly when its cue word is spoken):
  type: object (a hologram model; set "object": one of {objects}), box, sphere, cylinder, cone, torus, prism,
        panel (a floating screen), ring, helix, wave (oscillating signal), surface (moving 3D terrain), particles (a swarm;
        "count" 40-200), link (glowing arc with packets between two elements: "from" and "to" are element indexes),
        beam (straight laser between "from" and "to"), bars ("values": 2-8 numbers), donut ("values": shares), line
        ("values": a trend), matrix (grid of cells lighting up; "count" 3-7), network (node graph; "count" 5-14),
        gauge ("value" like "73%"), counter (a big number that counts up; "value"), text (a big word: "label"),
        orbit (satellites circling), stack (layers; "count" 2-5), tunnel (rings rushing into depth)
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
- Every element needs a cue (exact words from that scene's lines, in speaking order). Links/beams need valid from/to.
- Total narration 140-200 words. Accurate, specific facts and real numbers only. Casual, clear, no emojis/markdown.
{avoid}- "youtube": {{"title": max 70 chars ending " #shorts", "description": 2 sentences + 5 hashtags, "tags": 6-8}},
  "instagram_caption": 2-3 short lines + "Save this for later." + 6-8 hashtags.
Return ONLY JSON: {{"topic", "scenes": [{{"title", "lines": [...], "visual": {{...}}}}], "youtube", "instagram_caption"}}
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
        lines = [re.sub(r"\s+", " ", str(x)).strip().replace("**", "") for x in (s.get("lines") or []) if str(x).strip()]
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
            if t == "text" and not o["label"]:
                raise ValueError(f"scene {i + 1}: text element needs a label")
            types_all.add(t)
            els.append(o)
        if len({e["type"] for e in els}) < 2:
            raise ValueError(f"scene {i + 1} uses one element type - use at least 2")
        lay = v.get("layout")
        if lay not in C_LAYOUTS:
            raise ValueError(f"scene {i + 1}: layout must be one of {C_LAYOUTS}")
        if lay in layouts:
            raise ValueError(f"layout {lay!r} used twice - every scene needs a different layout")
        layouts.append(lay)
        vis = {"layout": lay, "elements": els,
               "camera": v.get("camera") if v.get("camera") in C_CAMS else random.choice(C_CAMS),
               "transition": v.get("transition") if v.get("transition") in C_TRANS else random.choice(C_TRANS)}
        if i == 0:
            vis["hook"] = True
        if i == len(scenes) - 1:
            vis["cta"] = True
        sig = signature(vis)
        if sig in banned or sig in sigs:
            raise ValueError(f"scene {i + 1} repeats a composition used before ({sig}) - design a new one")
        sigs.append(sig)
        clean.append({"plate": "compose", "title": _clip(s.get("title"), 28), "lines": lines, "data": vis})
    if len(types_all) < 8:
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
    title = _clip(yt.get("title") or sc.get("topic", "Explained"), 95)
    if "#shorts" not in title.lower():
        title = title[:86] + " #shorts"
    return {"topic": sc.get("topic", ""), "scenes": clean, "format": " > ".join(layouts), "signatures": sigs,
            "youtube": {"title": title, "description": str(yt.get("description", ""))[:4500],
                        "tags": [str(t)[:30] for t in (yt.get("tags") or [])][:10]},
            "instagram_caption": str(sc.get("instagram_caption", ""))[:2100]}


def write(topic, banned=(), recent=(), angle=None, tries=6, seed=0):
    rng = random.Random(seed)
    n = rng.choice([7, 8, 8, 9])
    avoid = ""
    if angle:
        avoid += f"- STORY ANGLE ({angle[0]}): {angle[1]} Explain it in a way this channel has not used before.\n"
    if recent:
        avoid += ("- Recent videos used these layout sequences - build something structurally different:\n"
                  + "\n".join(f"    {r}" for r in list(recent)[-5:]) + "\n")
    banned = set(banned)
    fmt = dict(topic=topic, objects="|".join(OBJECTS), layouts=", ".join(C_LAYOUTS), cams=", ".join(C_CAMS),
               trans=", ".join(C_TRANS), n=n, avoid=avoid)
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
