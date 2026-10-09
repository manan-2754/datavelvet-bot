"""
Learn from your own numbers: pull YouTube stats for past posts, tell Gemini what worked,
and give better-performing series more of the upcoming slots.

Uses the YouTube Data API (views / likes / comments) with the existing upload token.
"""
import random
from datetime import datetime, timezone

SERIES_ORDER = ["How It Works", "Interview Prep", "System Design"]


def refresh_stats(state):
    """Attach fresh YouTube statistics to every post in state['posts'] (best effort)."""
    posts = [p for p in state.get("posts", []) if p.get("youtube_id")]
    if not posts:
        return 0
    try:
        from googleapiclient.discovery import build
        from youtube_upload import get_credentials
        yt = build("youtube", "v3", credentials=get_credentials(), cache_discovery=False)
    except Exception as e:
        print(f"  stats unavailable: {e}")
        return 0
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    n = 0
    for i in range(0, len(posts), 50):
        chunk = posts[i:i + 50]
        try:
            items = yt.videos().list(part="statistics", id=",".join(p["youtube_id"] for p in chunk)).execute().get("items", [])
        except Exception as e:
            print(f"  stats request failed: {e}")
            return n
        by_id = {it["id"]: it.get("statistics", {}) for it in items}
        for p in chunk:
            st = by_id.get(p["youtube_id"])
            if st is not None:
                p["stats"] = {"views": int(st.get("viewCount", 0)), "likes": int(st.get("likeCount", 0)),
                              "comments": int(st.get("commentCount", 0)), "checked": now}
                n += 1
    return n


def _score(p):
    st = p.get("stats") or {}
    return st.get("views", 0) + 25 * st.get("likes", 0) + 60 * st.get("comments", 0)


def _mature(state, min_hours=20):
    """Posts old enough for their numbers to mean something."""
    out = []
    now = datetime.now(timezone.utc)
    for p in state.get("posts", []):
        if p.get("stats") and (now - datetime.fromisoformat(p["time"])).total_seconds() > min_hours * 3600:
            out.append(p)
    return out


def insights_text(state):
    """A short performance brief for the script prompt (empty until there is enough data)."""
    posts = _mature(state)
    if len(posts) < 4:
        return ""
    ranked = sorted(posts, key=_score, reverse=True)

    def line(p):
        st = p["stats"]
        return (f'- "{p.get("topic")}" [{p.get("series", "?")}] hook: "{p.get("hook", "")}" -> '
                f'{st["views"]} views, {st["likes"]} likes, {st["comments"]} comments')
    return ("\nWHAT OUR AUDIENCE RESPONDS TO (from our own channel stats - learn from it):\n"
            "Best performing:\n" + "\n".join(line(p) for p in ranked[:3]) + "\n"
            "Worst performing:\n" + "\n".join(line(p) for p in ranked[-3:]) + "\n"
            "Write hooks, framing and pacing closer to the best ones and avoid what the worst ones did.\n")


def pick_series(state):
    """Rotate series, giving the best-performing ones more turns (with some exploration)."""
    counts = state.setdefault("series_counts", {})
    posts = _mature(state)
    avgs = {}
    for s in SERIES_ORDER:
        vals = [_score(p) for p in posts if p.get("series") == s]
        avgs[s] = sum(vals) / len(vals) if vals else None
    known = [v for v in avgs.values() if v is not None]
    if len(known) < 2:
        return min(SERIES_ORDER, key=lambda s: (counts.get(s, 0), SERIES_ORDER.index(s)))   # plain rotation
    base = (sum(known) / len(known)) or 1
    w = [max(0.35, (avgs[s] if avgs[s] is not None else base) / base) for s in SERIES_ORDER]
    total = sum(counts.get(s, 0) for s in SERIES_ORDER) or 1
    w = [wi * (1.2 - counts.get(s, 0) / total) for wi, s in zip(w, SERIES_ORDER)]
    return random.choices(SERIES_ORDER, weights=w)[0]


def summary(state):
    posts = [p for p in state.get("posts", []) if p.get("stats")]
    if not posts:
        return "no stats yet"
    best = max(posts, key=_score)
    return (f"{len(posts)} videos, {sum(p['stats']['views'] for p in posts)} total views, "
            f"best: {best.get('topic')!r} ({best['stats']['views']} views)")
