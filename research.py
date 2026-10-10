"""
Real sources for every script: before writing, the bot asks the LLM which English Wikipedia articles cover the topic
(falling back to Wikipedia search), fetches their text, and hands the writer a block of reference facts; the video's
description lists the sources it was checked against.
"""
import json
import re
import time

import requests

UA = {"User-Agent": "DataVelvetBot/1.0 (educational explainer channel; contact via YouTube @datavelvet)"}
API = "https://en.wikipedia.org/w/api.php"
STOP = {"how", "why", "what", "is", "are", "the", "a", "an", "so", "does", "do", "works", "work", "under", "hood", "really",
        "actually", "explained", "inside", "with", "from", "your", "fast", "faster", "it", "its", "in", "of", "to", "and", "for"}


def _get(params):
    for attempt in range(3):
        r = requests.get(API, params={**params, "format": "json"}, headers=UA, timeout=20)
        if r.status_code == 429:
            time.sleep(3 * (attempt + 1))
            continue
        r.raise_for_status()
        return r.json()
    r.raise_for_status()


def _search(q, n=3):
    return [h["title"] for h in _get({"action": "query", "list": "search", "srsearch": q, "srlimit": n}).get("query", {}).get("search", [])]


def _extract(title, chars=2600):
    pages = _get({"action": "query", "prop": "extracts", "explaintext": 1, "titles": title, "redirects": 1}).get("query", {}).get("pages", {})
    page = next(iter(pages.values()), {}) if pages else {}
    if "missing" in page:
        return "", title
    text = re.sub(r"\n==+[^=]+==+\n", "\n", page.get("extract", ""))
    return re.sub(r"\n{2,}", "\n", text).strip()[:chars], page.get("title", title)


def _titles_from_llm(topic, llm):
    try:
        res = json.loads(llm(f'Which 2 English Wikipedia articles best explain "{topic}" for a technical explainer video? '
                             'Return ONLY JSON: {"titles": ["Exact Article Title", "Exact Article Title"]}', label="source pick"))
        return [str(t) for t in (res.get("titles") or []) if str(t).strip()][:3]
    except Exception:
        return []


def gather(topic, max_pages=2, llm=None):
    """Returns {"facts": text block for the prompt, "sources": [urls]} - empty on any failure (never blocks a post)."""
    keys = [w for w in re.findall(r"[a-z0-9+#]+", topic.lower()) if len(w) >= 3 and w not in STOP]
    out, sources = [], []
    try:
        cands = _titles_from_llm(topic, llm) if llm else []
        if not cands:
            cands = [t for t in _search(" ".join(keys) or topic, 5) if sum(k in t.lower() for k in keys) >= min(2, len(keys))]
        for title in cands:
            if len(sources) >= max_pages:
                break
            txt, real = _extract(title)
            if len(txt) > 300:
                out.append(f"[{real}]\n{txt}")
                sources.append("https://en.wikipedia.org/wiki/" + real.replace(" ", "_"))
            time.sleep(0.5)
    except Exception as e:
        print(f"  research unavailable ({e})")
    return {"facts": "\n\n".join(out)[:5000], "sources": sources}
