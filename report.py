"""
Weekly health report by email: posts made / missed, failures, views and reach, best and worst videos, what the
learning loop concluded, whether posting is throttled, and the series progress.

  python report.py            # send the report (cloud: weekly-report.yml, Mondays)
  python report.py --print    # just print it
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
try:
    from dotenv import load_dotenv
    load_dotenv(BASE / ".env", override=True)
except ImportError:
    pass


def build(state, days=7):
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    posts = [p for p in state.get("posts", []) if datetime.fromisoformat(p["time"]) >= since]
    runs = [r for r in state.get("runs", []) if datetime.fromisoformat(r["time"]) >= since]
    fails = [r for r in runs if not r.get("ok")]
    yt = sum((p.get("stats") or {}).get("yt_views", 0) for p in posts)
    ig = sum((p.get("stats") or {}).get("ig_views", 0) or (p.get("stats") or {}).get("ig_reach", 0) for p in posts)
    rated = sorted([p for p in posts if (p.get("stats") or {}).get("score") is not None], key=lambda p: p["stats"]["score"], reverse=True)
    both = sum(1 for p in posts if p.get("youtube_id") and p.get("instagram_id"))
    L = [f"DataVelvet bot - weekly report ({since:%b %d} - {now:%b %d})", "",
         f"Videos posted: {len(posts)} of ~{days * 4} slots ({both} on both platforms)",
         f"Failed runs: {len(fails)}" + (f"  (last: {fails[-1].get('error', '')[:160]})" if fails else ""),
         f"YouTube views (posts this week): {yt:,}", f"Instagram views/reach (posts this week): {ig:,}", ""]
    if rated:
        L.append("Best videos:")
        for p in rated[:3]:
            L.append(f"  {p['stats']['score']:>8.0f}  {p['topic']}  https://youtube.com/shorts/{p.get('youtube_id', '')}")
        L.append("Weakest videos:")
        for p in rated[-2:]:
            L.append(f"  {p['stats']['score']:>8.0f}  {p['topic']}")
        L.append("")
    ins = state.get("insights") or {}
    if ins.get("best"):
        L.append(f"What the bot learned (from {ins.get('n')} rated videos):")
        for f, v in ins["best"].items():
            if v:
                L.append(f"  works best  - {f}: {', '.join(v)}")
        for f, v in (ins.get("worst") or {}).items():
            if v:
                L.append(f"  works worst - {f}: {', '.join(v)}")
        L.append("")
    th = state.get("throttle")
    L.append(f"Posting throttle: {'ON until ' + th['until'] + ' (' + th.get('reason', '') + ')' if th else 'off'}")
    s = state.get("series") or {}
    if s:
        L.append(f"Current series: {s.get('name')} - episode {s.get('ep')}")
    return "\n".join(L)


def main():
    state = json.loads((BASE / "state.json").read_text(encoding="utf-8")) if (BASE / "state.json").exists() else {}
    text = build(state)
    if "--print" in sys.argv:
        print(text)
        return 0
    from notify import send_email
    send_email("DataVelvet weekly report", text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
