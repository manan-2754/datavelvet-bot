"""
Long-form YouTube videos (8-10 min, landscape 16:9), made natively with the engine in the reference "holo bot" style:
an AI outline of 7-9 chapters, then every chapter composed scene by scene from scratch (own layouts, 3D holograms,
cameras, entrances, transitions), with no scene composition ever reused - not across chapters, not across videos,
not from the Shorts. The style genome (palette, type, grid, glass, cameras) is generated fresh per video.

State lives in long_state.json (separate from the Shorts' state.json, so the two cloud jobs never collide).
"""
import json
import random
import time
from datetime import datetime, timezone
from pathlib import Path

import composer
import research
from writer import llm

BASE = Path(__file__).resolve().parent
LONG_STATE = BASE / "long_state.json"
SERIES_NAMES = ["System Design", "How the Internet Works", "Under the Hood", "AI Explained", "Security Decoded"]

OUTLINE = """You plan long-form (8-10 minute) YouTube deep dives for "DataVelvet", a premium 3D motion-graphics tech
explainer channel. {pick}
Do NOT repeat any of these past long-form videos: {used}

Plan ONE video with {n} chapters that build on each other like a story: start from something the viewer already
knows, raise a question, go one layer deeper each chapter, and pay everything off at the end. Every chapter needs a
concrete angle (a real number, a failure story, a comparison, a "what actually happens" walkthrough) - no fluff.
Every title and "covers" line must be technically TRUE as written: surprising is good, a false or oversimplified
premise is not (a strict fact-checker reviews every chapter and rejects false framing).
Return ONLY JSON:
{{"topic": the subject in a few words, "title": YouTube title max 80 chars (searchable + curiosity, no hashtags, no
"#shorts"), "titles": 3 alternative titles, "description": 3 sentences on what the viewer will understand,
"tags": 10-14 search tags, "chapters": [{{"title": max 40 chars, "covers": one sentence on exactly what this chapter
explains, with the key facts}}] ({n} items)}}"""


def load_long():
    st = json.loads(LONG_STATE.read_text(encoding="utf-8")) if LONG_STATE.exists() else {}
    for k in ("videos", "scene_signatures", "used_topics"):
        st.setdefault(k, [])
    return st


def save_long(st):
    LONG_STATE.write_text(json.dumps(st, indent=2, ensure_ascii=False), encoding="utf-8")


def outline(state, long_st, topic=None, n=8):
    shorts = [t for t in state.get("used_topics", [])][-40:]
    pick = (f'The topic is: "{topic}".' if topic else
            "Pick ONE broad, evergreen, highly searched topic in one of these series: " + ", ".join(SERIES_NAMES) +
            ". It can go deeper on subjects our Shorts touched recently: " + "; ".join(shorts[-15:]) + ".")
    used = "; ".join(v.get("topic", "") for v in long_st["videos"][-60:]) or "(none yet)"
    for i in range(3):
        try:
            o = json.loads(llm(OUTLINE.format(pick=pick, used=used, n=n), label="long-form outline"))
            ch = [c for c in (o.get("chapters") or []) if isinstance(c, dict) and c.get("title") and c.get("covers")]
            if len(ch) >= 6:
                o["chapters"] = ch[:9]
                return o
            raise ValueError(f"only {len(ch)} usable chapters")
        except Exception as e:
            print(f"  outline {i + 1} rejected: {e}")
    raise RuntimeError("no usable long-form outline")


FIX = """A fact-checker rejected every draft of this chapter of a tech explainer video:
chapter: {chapter}
reviewer: {errors}
Rewrite the chapter plan so it is technically accurate (keep it interesting). Return ONLY JSON: {{"title": max 40 chars,
"covers": one accurate sentence on what the chapter explains}}"""


def fix_chapter(c, errors):
    try:
        j = json.loads(llm(FIX.format(chapter=json.dumps(c, ensure_ascii=False), errors=errors[:1500]), label="chapter fix"))
        if j.get("title") and j.get("covers"):
            return {"title": str(j["title"])[:60], "covers": str(j["covers"])[:400]}
    except Exception as e:
        print(f"  chapter fix failed: {e}")
    return c


def write(state, long_st, topic=None, seed=None):
    rng = random.Random(seed or time.time_ns())
    o = outline(state, long_st, topic, n=rng.choice([7, 8, 8, 9]))
    whole, chapters = o.get("title") or o["topic"], o["chapters"]
    print(f"📖 Long-form: {whole}  ({len(chapters)} chapters)")
    facts = research.gather(o.get("topic") or whole, llm=llm)
    print(f"📚 Research: {len(facts['sources'])} source(s)")
    banned = set(state.get("scene_signatures", [])) | set(long_st["scene_signatures"])
    scenes, sigs, layouts, reviews, dropped = [], [], [], [], []
    for k, c in enumerate(chapters, 1):
        print(f"🎬 Chapter {k}/{len(chapters)}: {c['title']}")
        ch = {"k": k, "n": len(chapters), "whole": whole, "title": c["title"], "covers": c["covers"],
              "prev": chapters[k - 2]["title"] if k > 1 else None, "next": chapters[k]["title"] if k < len(chapters) else None}
        try:
            sc = composer.write(f'{whole} - chapter {k}: {c["title"]}', banned=banned, recent=layouts[-5:],
                                seed=rng.randrange(1 << 62), facts=facts, level="engineer", chapter=ch)
        except RuntimeError as e:                # usually a false premise in the plan: fix the chapter, try once more
            c = fix_chapter(c, str(e))
            ch.update(title=c["title"], covers=c["covers"])
            chapters[k - 1] = c
            print(f"  chapter re-planned as: {c['title']}")
            try:
                sc = composer.write(f'{whole} - chapter {k}: {c["title"]}', banned=banned, recent=layouts[-5:],
                                    seed=rng.randrange(1 << 62), facts=facts, level="engineer", chapter=ch)
            except RuntimeError as e2:          # still failing: drop this chapter rather than the whole video
                if k == len(chapters) or len(chapters) - len(dropped) - 1 < 5:
                    raise
                dropped.append(k)
                print(f"  chapter {k} dropped ({str(e2)[:120]})")
                continue
        for s in sc["scenes"]:
            s["chapter"] = k
            s["data"]["chapter"] = {"k": k, "n": len(chapters), "title": c["title"]}
        scenes += sc["scenes"]
        sigs += sc.get("signatures", [])
        banned |= set(sc.get("signatures", []))
        layouts.append(sc.get("format"))
        if sc.get("review"):
            reviews.append(sc["review"].get("score"))
    kept = sorted({s["chapter"] for s in scenes})          # renumber if a chapter was dropped
    for s in scenes:
        s["chapter"] = kept.index(s["chapter"]) + 1
        s["data"]["chapter"].update(k=s["chapter"], n=len(kept))
    title = composer.best_title([t for t in [whole, *(o.get("titles") or [])] if isinstance(t, str) and t.strip()])
    return {"topic": o.get("topic") or whole, "long": True, "scenes": scenes, "signatures": sigs,
            "format": " | ".join(layouts), "chapters": [c["title"] for k, c in enumerate(chapters, 1) if k not in dropped], "level": "engineer",
            "youtube": {"title": title.replace("#shorts", "").strip()[:95], "description": str(o.get("description", ""))[:1500],
                        "tags": [str(t)[:30] for t in (o.get("tags") or [])][:14]},
            "instagram_caption": "", "sources": facts["sources"],
            "review": {"chapter_scores": reviews}}


def chapter_marks(script):
    """YouTube chapter timestamps from the narration timings (first chapter at 0:00)."""
    ly = json.loads((BASE / "data" / "lyrics.json").read_text(encoding="utf-8"))
    first = {}
    for ln in ly["lines"]:
        k = script["scenes"][ln["scene"]].get("chapter")
        if k and k not in first:
            first[k] = ln["start"]
    out = []
    for k, title in enumerate(script.get("chapters", []), 1):
        s = 0 if k == 1 else int(max(0, first.get(k, 0) - 0.4))
        out.append(f"{s // 60}:{s % 60:02d} {title}")
    return out


def describe(script):
    """Adds the chapter list, sources and AI disclosure to the YouTube description (links are added by main.add_links)."""
    yt = script["youtube"]
    marks = chapter_marks(script)
    src = script.get("sources") or []
    yt["description"] = (yt.get("description", "") + "\n\nChapters:\n" + "\n".join(marks) +
                         ("\n\nSources:\n" + "\n".join(src[:8]) if src else "") +
                         "\n\nScript fact-checked against these sources by AI. Visuals and voice are AI-generated."
                         "\n\n#techexplained #computerscience #programming")[:4900]
    return marks


def remember(long_st, script, video_id):
    long_st["videos"].append({"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "topic": script["topic"],
                              "title": script["youtube"]["title"], "youtube_id": video_id,
                              "style": (script.get("style") or {}).get("name")})
    long_st["used_topics"].append(script["topic"])
    long_st["scene_signatures"].extend(script.get("signatures", []))
