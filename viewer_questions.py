"""
Viewer questions -> videos. Reads new comments on the channel's YouTube videos and Instagram Reels, keeps the real
questions, lets the LLM pick the ones that make a good, accurate explainer, and queues them as topics. The video then
opens with "@user asked: ...", which builds community and shows real human interaction on the channel.
"""
import json
import os
import re

import requests

QUESTION = re.compile(r"\?|^(how|why|what|when|where|can|could|does|do|is|are|will|should|which)\b", re.I)
PICK = """Viewers left these comments on a tech-explainer channel (3D animated Shorts about everyday tech):
{items}
Pick the comments that ask a real question which would make a good, accurate 45-second explainer about how technology
works (skip spam, insults, personal requests, off-topic, or questions about the channel itself). For each pick, write a
short video topic (max 60 chars, e.g. "Why your phone slows down when storage is full").
Return ONLY JSON: {{"picks": [{{"i": comment number, "topic": "..."}}]}}"""


def _youtube(seen):
    from youtube_upload import _api
    yt = _api()
    me = yt.channels().list(part="id", mine=True).execute()["items"][0]["id"]
    res = yt.commentThreads().list(part="snippet", allThreadsRelatedToChannelId=me, maxResults=50, order="time",
                                   textFormat="plainText").execute()
    out = []
    for it in res.get("items", []):
        c = it["snippet"]["topLevelComment"]["snippet"]
        if it["id"] in seen or (c.get("authorChannelId") or {}).get("value") == me:
            continue
        out.append({"id": it["id"], "platform": "YouTube", "user": c.get("authorDisplayName", ""), "text": c.get("textDisplay", "")})
    return out


def _instagram(state, seen):
    tok = os.getenv("IG_ACCESS_TOKEN", "").strip()
    if not tok:
        return []
    me = requests.get("https://graph.instagram.com/v21.0/me", params={"fields": "username", "access_token": tok}, timeout=30).json()
    out = []
    for p in [p for p in state.get("posts", []) if p.get("instagram_id")][-15:]:
        r = requests.get(f"https://graph.instagram.com/v21.0/{p['instagram_id']}/comments",
                         params={"fields": "id,text,username", "access_token": tok}, timeout=30)
        for c in (r.json().get("data") or []) if r.ok else []:
            if c["id"] in seen or c.get("username") == me.get("username"):
                continue
            out.append({"id": c["id"], "platform": "Instagram", "user": "@" + c.get("username", ""), "text": c.get("text", "")})
    return out


def collect(state, llm):
    """Adds new good viewer questions to state["viewer_questions"]; returns how many were queued."""
    seen = set(state.setdefault("seen_comments", []))
    found = []
    for name, fn in (("YouTube", lambda: _youtube(seen)), ("Instagram", lambda: _instagram(state, seen))):
        try:
            found += fn()
        except Exception as e:
            print(f"  viewer questions: {name} unavailable ({str(e)[:100]})")
    state["seen_comments"] = (list(seen) + [c["id"] for c in found])[-2000:]
    qs = [c for c in found if QUESTION.search(c["text"].strip()) and 8 <= len(c["text"]) <= 300]
    if not qs:
        return 0
    listing = "\n".join(f"{k}. [{c['platform']}] {c['user']}: {c['text'][:200]}" for k, c in enumerate(qs))
    try:
        picks = json.loads(llm(PICK.format(items=listing), label="viewer questions")).get("picks") or []
    except Exception as e:
        print(f"  viewer questions: picker unavailable ({e})")
        return 0
    queue = state.setdefault("viewer_questions", [])
    used = {q["topic"].lower() for q in queue} | {t.lower() for t in state.get("used_topics", [])}
    n = 0
    for p in picks:
        try:
            c = qs[int(p["i"])]
        except (KeyError, ValueError, IndexError, TypeError):
            continue
        topic = str(p.get("topic") or "").strip()[:80]
        if topic and topic.lower() not in used:
            queue.append({"topic": topic, "user": c["user"], "platform": c["platform"], "text": c["text"][:200]})
            used.add(topic.lower())
            n += 1
    return n


def hint(q):
    """Prompt text that makes the video answer the viewer by name."""
    return (f'- A viewer ({q["user"]} on {q["platform"]}) asked: "{q["text"]}". Scene 1 must open with '
            f'"{q["user"]} asked:" followed by their question in a few words, then answer it. Thank them in the last scene.\n')
