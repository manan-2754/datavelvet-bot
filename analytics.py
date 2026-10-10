"""
The learning loop. Every run, the bot pulls stats for its recent posts (YouTube views / likes / comments via the
read-only scope, Instagram reach / views / saves / shares / likes / comments via Graph insights), scores each video,
and learns which creative choices perform: story angle, layouts, element types, camera moves, colour family, voice,
music and length. The insights steer the next scripts (prompt hints) and the art director (weighted choices) -
novelty rules still apply, so it leans toward what works without ever repeating a video.
It also watches the reach trend and slows posting down if reach collapses (a shadow-ban / fatigue signal).
"""
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import requests

WEIGHTS = {"yt_views": 1, "yt_likes": 25, "yt_comments": 60, "ig_views": 1, "ig_reach": 0.5, "ig_saved": 40, "ig_shares": 60,
           "ig_likes": 25, "ig_comments": 60}
FEATURES = ["angle", "layouts", "types", "cams", "hue", "voice", "music", "length", "level", "trend"]


def _now():
    return datetime.now(timezone.utc)


def _age_h(p):
    try:
        return (_now() - datetime.fromisoformat(p["time"])).total_seconds() / 3600
    except Exception:
        return 0


def collect(state, max_posts=40):
    """Refresh stats for posts that are 20 h - 30 days old and were not fetched in the last 12 h."""
    def stale(p):
        f = (p.get("stats") or {}).get("fetched")
        return not f or (_now() - datetime.fromisoformat(f)) > timedelta(hours=12)
    todo = [p for p in state.get("posts", [])[-max_posts:] if 20 <= _age_h(p) <= 24 * 30 and stale(p)]
    if not todo:
        return 0
    yt_ids = [p["youtube_id"] for p in todo if p.get("youtube_id")]
    yt = {}
    if yt_ids:
        try:
            from googleapiclient.discovery import build
            from youtube_upload import get_credentials
            api = build("youtube", "v3", credentials=get_credentials(), cache_discovery=False)
            for i in range(0, len(yt_ids), 50):
                res = api.videos().list(part="statistics", id=",".join(yt_ids[i:i + 50])).execute()
                for it in res.get("items", []):
                    s = it.get("statistics", {})
                    yt[it["id"]] = {"yt_views": int(s.get("viewCount", 0)), "yt_likes": int(s.get("likeCount", 0)),
                                    "yt_comments": int(s.get("commentCount", 0))}
        except Exception as e:
            print(f"  analytics: YouTube stats unavailable ({e})")
    tok = os.getenv("IG_ACCESS_TOKEN", "").strip()
    n = 0
    for p in todo:
        st = dict(yt.get(p.get("youtube_id"), {}))
        if tok and p.get("instagram_id"):
            try:
                r = requests.get(f"https://graph.instagram.com/v21.0/{p['instagram_id']}/insights", timeout=30,
                                 params={"metric": "reach,saved,shares,views,likes,comments", "access_token": tok})
                if r.ok:
                    for m in r.json().get("data", []):
                        st[f"ig_{m['name']}"] = int((m.get("values") or [{}])[0].get("value", 0))
            except Exception as e:
                print(f"  analytics: Instagram insights unavailable ({e})")
        if st:
            st["score"] = round(sum(WEIGHTS.get(k, 0) * v for k, v in st.items() if isinstance(v, (int, float))), 1)
            st["fetched"] = _now().isoformat(timespec="seconds")
            p["stats"] = st
            n += 1
    return n


def _vals(p, f):
    v = (p.get("features") or {}).get(f)
    if v is None:
        return []
    return [str(x) for x in v] if isinstance(v, list) else [str(v)]


def learn(state):
    rated = [p for p in state.get("posts", []) if (p.get("stats") or {}).get("score") is not None and p.get("features")]
    ins = {"n": len(rated), "updated": _now().isoformat(timespec="seconds"), "best": {}, "worst": {}, "lift": {}}
    if len(rated) >= 4:
        mean = (sum(p["stats"]["score"] for p in rated) / len(rated)) or 1
        for f in FEATURES:
            acc = defaultdict(list)
            for p in rated:
                for v in set(_vals(p, f)):
                    acc[v].append(p["stats"]["score"])
            lift = {v: round((sum(s) / len(s)) / mean, 2) for v, s in acc.items() if len(s) >= 2}
            if not lift:
                continue
            order = sorted(lift, key=lift.get, reverse=True)
            ins["lift"][f] = lift
            ins["best"][f] = [v for v in order[:3] if lift[v] > 1.1]
            ins["worst"][f] = [v for v in order[-3:] if lift[v] < 0.85]
    state["insights"] = ins
    return ins


def hints(state):
    """Prompt text for the script writer."""
    ins = state.get("insights") or {}
    if ins.get("n", 0) < 4:
        return ""
    keys = ("angle", "layouts", "types", "cams", "level", "length")
    good = [f"{f}: {', '.join(v)}" for f, v in ins.get("best", {}).items() if v and f in keys]
    bad = [f"{f}: {', '.join(v)}" for f, v in ins.get("worst", {}).items() if v and f in keys]
    if not good and not bad:
        return ""
    txt = f"- AUDIENCE DATA from the last {ins['n']} videos (lean toward what works, but stay original):\n"
    if good:
        txt += "    performed best -> " + " | ".join(good) + "\n"
    if bad:
        txt += "    performed worst -> " + " | ".join(bad) + "\n"
    return txt


def weight(state, feature, value):
    """Multiplier for weighted random choices (1.0 = neutral)."""
    lift = ((state.get("insights") or {}).get("lift") or {}).get(feature, {})
    return max(0.35, min(2.5, float(lift.get(str(value), 1.0))))


def reach_check(state):
    """Throttle posting for 48 h if the last 5 videos score < 40 % of the 10 before them."""
    th = state.get("throttle") or {}
    if th.get("until") and datetime.fromisoformat(th["until"]) < _now():
        state.pop("throttle", None)
        th = {}
    rated = [p for p in state.get("posts", []) if (p.get("stats") or {}).get("score") is not None]
    if len(rated) >= 15 and not th:
        a = sum(p["stats"]["score"] for p in rated[-5:]) / 5
        b = sum(p["stats"]["score"] for p in rated[-15:-5]) / 10
        if b > 0 and a / b < 0.4:
            state["throttle"] = {"until": (_now() + timedelta(hours=48)).isoformat(timespec="seconds"), "skip_every": 2,
                                 "reason": f"reach fell to {a / b:.0%} of the previous 10 videos"}
            print(f"  ⚠️ reach dropped ({a / b:.0%}) - posting every other slot for 48 h")
    return state.get("throttle")


def should_skip(state):
    th = state.get("throttle")
    if not th:
        return False
    k = state.get("throttle_counter", 0) + 1
    state["throttle_counter"] = k
    return k % int(th.get("skip_every", 2)) != 0
