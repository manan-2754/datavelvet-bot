"""
Trend-aware topics: reads what developers are talking about right now (Hacker News front page, fastest-rising new
GitHub repos, r/programming) and asks the LLM for ONE timely, explainable concept the channel has not covered yet.
Used for one of the daily slots; the rest come from the evergreen topic list.
"""
import json
from datetime import datetime, timedelta, timezone

import requests

UA = {"User-Agent": "DataVelvetBot/1.0 (educational explainer channel)"}


def hacker_news(n=25):
    ids = requests.get("https://hacker-news.firebaseio.com/v0/topstories.json", timeout=20).json()[:n]
    out = []
    for i in ids:
        try:
            it = requests.get(f"https://hacker-news.firebaseio.com/v0/item/{i}.json", timeout=10).json() or {}
            if it.get("title"):
                out.append({"title": it["title"], "url": it.get("url") or f"https://news.ycombinator.com/item?id={i}", "score": it.get("score", 0)})
        except Exception:
            continue
    return out


def github_rising(n=10):
    since = (datetime.now(timezone.utc) - timedelta(days=10)).strftime("%Y-%m-%d")
    r = requests.get("https://api.github.com/search/repositories", headers=UA, timeout=20,
                     params={"q": f"created:>{since}", "sort": "stars", "order": "desc", "per_page": n})
    return [{"title": f"{x['full_name']}: {x.get('description') or ''}"[:160], "url": x["html_url"], "score": x["stargazers_count"]}
            for x in r.json().get("items", [])]


def reddit(n=15, sub="technology"):
    r = requests.get(f"https://www.reddit.com/r/{sub}/hot.json", params={"limit": n}, headers=UA, timeout=20)
    return [{"title": c["data"]["title"], "url": "https://reddit.com" + c["data"]["permalink"], "score": c["data"]["score"]}
            for c in r.json().get("data", {}).get("children", [])]


FEEDS = [("Google News Tech", "https://news.google.com/rss/headlines/section/topic/TECHNOLOGY?hl=en-US&gl=US&ceid=US:en"),
         ("The Verge", "https://www.theverge.com/rss/index.xml"),
         ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/index")]


def rss(url, n=15):
    """Headlines from an RSS/Atom feed (free, no key)."""
    import xml.etree.ElementTree as ET
    root = ET.fromstring(requests.get(url, headers=UA, timeout=20).content)
    out = []
    for it in root.iter():
        tag = it.tag.split("}")[-1]
        if tag in ("item", "entry"):
            t = next((c.text for c in it if c.tag.split("}")[-1] == "title"), None)
            lk = next((c.text or c.get("href") for c in it if c.tag.split("}")[-1] == "link"), "")
            if t:
                out.append({"title": t.strip(), "url": lk or "", "score": 0})
        if len(out) >= n:
            break
    return out


def gather():
    items = []
    for name, fn in [*((nm, (lambda u=u: rss(u))) for nm, u in FEEDS), ("Hacker News", lambda: hacker_news(15))]:
        try:
            items += [{**x, "src": name} for x in fn()]
        except Exception as e:
            print(f"  trends: {name} unavailable ({e})")
    return items


PROMPT = """You pick topics for "DataVelvet", a 45-second 3D explainer channel about the tech everyday people use:
phones, laptops, apps, the internet, Wi-Fi, batteries, AI tools, privacy and security.
Here is what is trending in tech news RIGHT NOW:
{items}

Already covered (do NOT pick these or near-duplicates): {used}

Pick ONE topic that is (1) clearly connected to something trending above, (2) an explainable mechanism that a normal
phone or laptop user cares about (e.g. "Why the outage took down half the internet", "How the new iPhone camera sees
in the dark", "How AI chatbots remember your chats"), not developer-only internals, gossip or a product ad,
(3) accurate to explain in 45 seconds. Return ONLY JSON:
{{"topic": "How/Why/What ... (max 60 chars)", "why": "one line: which trending item it connects to", "source_index": n}}"""


def pick(used, llm):
    items = gather()
    if not items:
        return None
    items = sorted(items, key=lambda x: -x.get("score", 0))[:40]
    listing = "\n".join(f"{i}. [{x['src']}] {x['title']}" for i, x in enumerate(items))
    try:
        res = json.loads(llm(PROMPT.format(items=listing, used=", ".join(list(used)[-60:])), label="trend pick"))
        topic = str(res.get("topic", "")).strip()
        if not topic or topic in used:
            return None
        idx = res.get("source_index")
        src = items[idx]["url"] if isinstance(idx, int) and 0 <= idx < len(items) else None
        return {"topic": topic[:80], "why": str(res.get("why", ""))[:160], "sources": [src] if src else []}
    except Exception as e:
        print(f"  trend pick failed ({e})")
        return None
