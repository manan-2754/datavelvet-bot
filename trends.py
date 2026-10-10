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


def reddit(n=15):
    r = requests.get("https://www.reddit.com/r/programming/hot.json", params={"limit": n}, headers=UA, timeout=20)
    return [{"title": c["data"]["title"], "url": "https://reddit.com" + c["data"]["permalink"], "score": c["data"]["score"]}
            for c in r.json().get("data", {}).get("children", [])]


def gather():
    items = []
    for name, fn in (("Hacker News", hacker_news), ("GitHub", github_rising), ("Reddit", reddit)):
        try:
            items += [{**x, "src": name} for x in fn()]
        except Exception as e:
            print(f"  trends: {name} unavailable ({e})")
    return items


PROMPT = """You pick topics for "DataVelvet", a 60-90 second explainer channel about software, systems and how tech works.
Here is what developers are discussing RIGHT NOW:
{items}

Already covered (do NOT pick these or near-duplicates): {used}

Pick ONE topic that is (1) clearly connected to something trending above, (2) an explainable CONCEPT or mechanism
(e.g. "How WebGPU renders in the browser", "Why Rust's borrow checker prevents data races"), not news gossip or a
product announcement, (3) accurate to explain in 60-90 seconds. Return ONLY JSON:
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
