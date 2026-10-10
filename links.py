"""
Affiliate + own-offer links, matched to each video's topic and added to the YouTube description and Instagram caption
(and, clickable, to the weekly long-form compilation's description).

Your links live in affiliates.json (or the GitHub variable AFFILIATES_JSON, same format) - see affiliates.example.json:
  {"bio": "https://your-link-in-bio-page",
   "links": [{"name": "...", "url": "https://...", "pitch": "short reason to click", "keywords": ["docker", "kubernetes"]},
             {"name": "My cheat sheet", "url": "https://...", "pitch": "...", "always": true}]}
Nothing is added while no links are configured. Every link block carries an affiliate disclosure.
"""
import json
import os
from pathlib import Path

BASE = Path(__file__).resolve().parent
DISCLOSURE = "Some links are affiliate links - I may earn a commission at no extra cost to you."


def load():
    raw = os.getenv("AFFILIATES_JSON", "").strip()
    try:
        if raw:
            return json.loads(raw)
        f = BASE / "affiliates.json"
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    except Exception as e:
        print(f"  affiliate links skipped (bad JSON: {e})")
        return {}


def pick(text, k=2, cfg=None):
    """The best-matching links for this text: keyword hits first, then 'always' offers."""
    cfg = load() if cfg is None else cfg
    low = f" {text.lower()} "
    scored = []
    for i, ln in enumerate(cfg.get("links") or []):
        if not (isinstance(ln, dict) and str(ln.get("url", "")).startswith("http")):
            continue
        hits = sum(1 for kw in ln.get("keywords") or [] if str(kw).lower().strip() and str(kw).lower() in low)
        if hits or ln.get("always"):
            scored.append((hits, -i, ln))
    return [ln for _, _, ln in sorted(scored, key=lambda x: (x[0], x[1]), reverse=True)[:k]]


def block(chosen):
    if not chosen:
        return ""
    rows = [f"🔗 {ln.get('pitch') or ln.get('name')}: {ln['url']}" for ln in chosen]
    return "\n".join(rows) + f"\n({DISCLOSURE})"


def apply(script):
    """Adds the matched links to the script's YouTube description and Instagram caption. Returns the chosen links."""
    cfg = load()
    series = (script.get("series") or {}).get("name") or ""
    chosen = pick(f"{script.get('topic', '')} {series}", cfg=cfg)
    if not chosen:
        return []
    yt = script.setdefault("youtube", {})
    yt["description"] = (yt.get("description", "") + "\n\n" + block(chosen))[:4900]
    names = ", ".join(ln.get("name") or "the tools" for ln in chosen)
    where = "in bio" if cfg.get("bio") else "on our YouTube"
    script["instagram_caption"] = (script.get("instagram_caption", "") + f"\n\n🔗 {names}: link {where} (affiliate)")[:2150]
    script["affiliates"] = [ln["url"] for ln in chosen]
    return chosen
