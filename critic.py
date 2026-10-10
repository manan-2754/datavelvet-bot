"""
Art critic before the expensive render: renders one still from the middle of every scene (cheap), shows them to a
vision model, and fixes what it flags - cramped / off-screen framing pulls the camera back, empty frames push it in,
lifeless scenes get motion - by editing the scene data in data/lyrics.json. Never blocks a post: any failure = skip.
"""
import base64
import io
import json
import os
import subprocess
from pathlib import Path

import requests

BASE = Path(__file__).resolve().parent
MODELS = ["gemini-3.5-flash", "gemini-flash-latest", "gemini-3.1-flash-lite"]
RUBRIC = """You are a strict motion-design art director reviewing still frames from a vertical (9:16) explainer video,
one frame from the middle of each scene, in order. Judge only what you SEE. For each frame list issues from exactly
this set: "offscreen" (key elements cut off by the frame edge), "cramped" (overlapping / cluttered, labels colliding),
"empty" (large empty areas, subject too small or missing), "unreadable" (text too small or low contrast), "dull" (static,
flat, nothing striking). Return ONLY JSON:
{"overall": 1-10, "scenes": [{"scene": 1, "score": 1-10, "issues": ["..."]}]}"""


def _frames(times, env, tool):
    out = BASE / "out" / "critic"
    out.mkdir(parents=True, exist_ok=True)
    for f in out.glob("*.png"):
        f.unlink()
    subprocess.run([tool("bun"), "scripts/render.ts", "stills", "--t", ",".join(f"{t:.2f}" for t in times), "--out", str(out)],
                   cwd=BASE / "app", env=env, check=True, capture_output=True)
    return sorted(out.glob("*.png"), key=lambda p: float(p.stem.split("_")[1]))


def _jpeg_b64(path):
    from PIL import Image
    im = Image.open(path).convert("RGB")
    im.thumbnail((360, 640))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=80)
    return base64.b64encode(buf.getvalue()).decode()


def _ask(images):
    key = os.getenv("GEMINI_API_KEY", "").strip()
    parts = [{"text": RUBRIC}] + [{"inline_data": {"mime_type": "image/jpeg", "data": b}} for b in images]
    last = RuntimeError("no GEMINI_API_KEY")
    for m in (MODELS if key else []):
        try:
            r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent",
                              headers={"x-goog-api-key": key}, timeout=180,
                              json={"contents": [{"parts": parts}], "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2}})
            r.raise_for_status()
            return json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"]), m
        except Exception as e:
            last = e
    if os.getenv("ANTHROPIC_API_KEY", "").strip():      # paid backup: Claude Haiku reads the frames
        try:
            import anthropic
            from writer import CLAUDE_MODEL, _json_text
            content = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b}} for b in images]
            content.append({"type": "text", "text": RUBRIC})
            r = anthropic.Anthropic(timeout=180.0).messages.create(model=CLAUDE_MODEL, max_tokens=4000, output_config={"effort": "low"},
                                                                  messages=[{"role": "user", "content": content}])
            if r.stop_reason not in ("refusal", "max_tokens"):
                return json.loads(_json_text("".join(b.text for b in r.content if b.type == "text"))), CLAUDE_MODEL
            last = RuntimeError(f"Claude stopped: {r.stop_reason}")
        except Exception as e:
            last = e
    raise RuntimeError(f"vision models unavailable: {last}")


def review(env, tool):
    """Returns a short report string; edits data/lyrics.json in place when it fixes something."""
    ly_path = BASE / "data" / "lyrics.json"
    ly = json.loads(ly_path.read_text(encoding="utf-8"))
    scenes, lines = ly.get("scenes", []), ly.get("lines", [])
    if not scenes or not all(s.get("plate") == "compose" for s in scenes):
        return "critic: skipped (not a composed video)"
    times = []
    norm = lambda w: "".join(ch for ch in str(w).lower() if ch.isalnum())
    for i, sc in enumerate(scenes):
        ls = [l for l in lines if l.get("scene") == i]
        if not ls:
            times.append(0.5)
            continue
        words = [w for l in ls for w in l["words"]]
        cue_t = []
        for e in (sc.get("data") or {}).get("elements", []):   # judge the frame AFTER every element has appeared
            tok = norm((str(e.get("cue") or "").split() or [""])[0])
            hit = next((w for w in words if tok and norm(w["w"]) == tok), None)
            if hit:
                cue_t.append(hit["start"])
        mid = (ls[0]["start"] + ls[-1]["end"]) / 2
        times.append(min(ls[-1]["end"] - 0.15, max(mid, (max(cue_t) + 1.0) if cue_t else mid)))
    try:
        frames = _frames(times, env, tool)
        verdict, model = _ask([_jpeg_b64(f) for f in frames])
    except Exception as e:
        return f"critic: skipped ({e})"
    fixes = []
    for row in verdict.get("scenes", []):
        try:
            i = int(row.get("scene", 0)) - 1
        except (TypeError, ValueError):
            continue
        if not 0 <= i < len(scenes):
            continue
        d, iss = scenes[i].setdefault("data", {}), set(row.get("issues") or [])
        if iss & {"offscreen", "cramped"}:
            d["camDist"] = round(float(d.get("camDist", 1)) * 1.25, 2)
            fixes.append(f"{i + 1}:pull back")
        elif "empty" in iss:
            d["camDist"] = round(float(d.get("camDist", 1)) * 0.82, 2)
            fixes.append(f"{i + 1}:push in")
        if "dull" in iss:
            for e in d.get("elements", []):
                if e.get("idle") in (None, "none"):
                    e["idle"] = "spin" if e.get("type") not in ("text", "counter", "panel", "code") else "float"
            if d.get("transition") in (None, "cut", "fade"):
                d["transition"] = "zoom"
            fixes.append(f"{i + 1}:more motion")
        if "unreadable" in iss:
            d["labelScale"] = 1.2
            fixes.append(f"{i + 1}:bigger labels")
    if fixes:
        ly_path.write_text(json.dumps(ly, indent=1, ensure_ascii=False), encoding="utf-8")
    return f"critic ({model}): overall {verdict.get('overall')}/10, fixes: {', '.join(fixes) or 'none needed'}"
