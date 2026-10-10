"""
Art director: invents a brand-new visual identity ("style genome") and storytelling angle for every video, and keeps
it different from every style still in memory. A style is remembered only for 3 hours after its video was posted;
after that it is forgotten and its ingredients can come back.

The genome is written into data/lyrics.json as `style`; the engine applies it before anything is built:
palette (every colour in every shader), hologram tints, typography (width / weight / case), graph-paper density,
caption size and position, post-processing (bloom, vignette, grain, aberration, halation), the 2D camera feel and,
per scene, the 3D camera move, reveal style, floor and spin direction.
"""
import colorsys
import random
from datetime import datetime, timedelta, timezone

FORGET_AFTER = timedelta(hours=3)
CAM_MODES = ["fly", "orbit", "crane", "dolly", "low", "top", "dutch", "spiral", "whip", "push"]
REVEALS = ["scan", "assemble", "draw", "glitch"]
FLOORS = ["grid", "polar", "dots", "hex"]
CASES = ["title", "upper", "lower"]
HOOK_MOTIFS = ["dial", "chart", "number", "strike", "holo"]
ANGLES = [
    ("myth-busting", "Open with a common misconception, then take it apart scene by scene."),
    ("analogy", "Carry ONE everyday analogy (kitchen, traffic, post office...) through the whole video."),
    ("journey", "Follow one single request / object / byte as it travels through the system, scene by scene."),
    ("numbers-first", "Lead every scene with a concrete number, then explain what it means."),
    ("question-chain", "Each scene answers the question the previous scene raised; end each scene on a new question."),
    ("build-it", "Build the idea from scratch: start with the naive version, add one piece per scene."),
    ("failure-first", "Start from something breaking or going wrong, then show how the design prevents it."),
    ("zoom-out", "Start at the tiniest detail and zoom out one level per scene to the big picture."),
    ("countdown", "Structure it as a countdown of the key ideas, most surprising last."),
    ("versus", "Frame it as a contest between two approaches, ending with when to use each."),
]
HUE_NAMES = [(15, "Ember"), (35, "Amber"), (55, "Saffron"), (85, "Lime"), (130, "Jade"), (165, "Teal"), (195, "Cyan"),
             (215, "Cobalt"), (240, "Indigo"), (270, "Violet"), (300, "Orchid"), (330, "Magenta"), (360, "Crimson")]
MOODS = ["Nocturne", "Signal", "Blueprint", "Circuit", "Aurora", "Static", "Prism", "Vector", "Pulse", "Lattice",
         "Drift", "Flux", "Halo", "Cipher", "Monolith", "Neon", "Quartz", "Tide", "Ion", "Verge"]


def _hex(h, s, l):
    r, g, b = colorsys.hls_to_rgb((h % 360) / 360, max(0, min(1, l)), max(0, min(1, s)))
    return "#%02X%02X%02X" % (round(r * 255), round(g * 255), round(b * 255))


def _hue_dist(a, b):
    d = abs(a - b) % 360
    return min(d, 360 - d)


def _name(h):
    return next(n for lim, n in HUE_NAMES if h % 360 <= lim)


def _now():
    return datetime.now(timezone.utc)


def prune(state, now=None):
    """Forget styles whose video was posted more than 3 hours ago."""
    now = now or _now()
    keep = [m for m in state.get("style_memory", [])
            if not (m.get("posted_at") and datetime.fromisoformat(m["posted_at"]) + FORGET_AFTER < now)]
    state["style_memory"] = keep
    return keep


def remember(state, genome, fmt, angle, posted_at=None):
    state.setdefault("style_memory", []).append({"posted_at": (posted_at or _now()).isoformat(timespec="seconds"),
                                                 "style": genome, "format": fmt, "angle": angle})


def recent_formats(state):
    return [m.get("format") for m in prune(state) if m.get("format")]


def pick_angle(state, rng=None):
    rng = rng or random.SystemRandom()
    used = {m.get("angle") for m in prune(state)}
    return rng.choice([a for a in ANGLES if a[0] not in used] or ANGLES)


def pick_hook(state, rng=None):
    rng = rng or random.SystemRandom()
    used = {(m.get("style") or {}).get("hook") for m in prune(state)}
    return rng.choice([h for h in HOOK_MOTIFS if h not in used] or HOOK_MOTIFS)


def _novel(g, mem):
    for m in mem:
        o = m.get("style") or {}
        if not o.get("_h"):
            continue
        if _hue_dist(g["_h"]["bg"], o["_h"]["bg"]) < 45 or _hue_dist(g["_h"]["signal"], o["_h"]["signal"]) < 45:
            return False
        if _hue_dist(g["_h"]["holo"], o["_h"]["holo"]) < 40:
            return False
        a, b = [s["cam"] for s in g["scenes"]], [s["cam"] for s in o.get("scenes", [])]
        if sum(x == y for x, y in zip(a, b)) > 0.3 * max(1, min(len(a), len(b))):
            return False
        if g["type"]["case"] == o["type"]["case"] and abs(g["type"]["wscale"] - o["type"]["wscale"]) < 0.15:
            return False
        if abs(g["grid"]["minor"] - o["grid"]["minor"]) < 6:
            return False
    return True


def _sequence(rng, options, n, avoid_seq=()):
    out = []
    for i in range(n):
        pool = [o for o in options if (not out or o != out[-1]) and (i >= len(avoid_seq) or o != avoid_seq[i])]
        out.append(rng.choice(pool or options))
    return out


def new_genome(state, n_scenes, rng=None, tries=400, hook=None):
    """A style no remembered video used; every field is generated fresh."""
    rng = rng or random.SystemRandom()
    mem = prune(state)
    last = (mem[-1].get("style") or {}) if mem else {}
    g = None
    for _ in range(tries):
        hb = rng.uniform(0, 360)
        hs = (hb + rng.choice([1, -1]) * rng.uniform(70, 200)) % 360
        hh = (hs + rng.choice([1, -1]) * rng.uniform(80, 180)) % 360
        bs, bl = rng.uniform(0.25, 0.55), rng.uniform(0.035, 0.065)
        palette = {
            "ink": _hex(hb, bs, bl), "ink2": _hex(hb, bs * 0.9, bl + 0.045),
            "graphite": _hex(hb, 0.1, rng.uniform(0.34, 0.42)), "ash": _hex(hb, 0.08, rng.uniform(0.58, 0.66)),
            "bone": _hex(hb + rng.uniform(-20, 20), rng.uniform(0.12, 0.35), rng.uniform(0.9, 0.95)),
            "signal": _hex(hs, rng.uniform(0.85, 1.0), rng.uniform(0.52, 0.6)),
            "ember": _hex(hs + 14, 1.0, rng.uniform(0.64, 0.7)), "blood": _hex(hs - 6, 0.85, rng.uniform(0.36, 0.42)),
        }
        holo = [_hex(hh, rng.uniform(0.75, 1.0), rng.uniform(0.6, 0.68)),
                _hex(hh + rng.choice([1, -1]) * rng.uniform(25, 50), rng.uniform(0.7, 1.0), rng.uniform(0.6, 0.7))]
        minor = rng.choice([16, 18, 20, 24, 28, 32, 36, 40])
        g = {
            "name": f"{_name(hb)} {rng.choice(MOODS)} / {_name(hs)} signal",
            "created": _now().isoformat(timespec="seconds"),
            "hook": hook,
            "tag": rng.choice(["chip", "bracket", "underline", "pill", "side"]),
            "_h": {"bg": round(hb, 1), "signal": round(hs, 1), "holo": round(hh, 1)},
            "palette": palette, "holo": holo,
            "type": {"wscale": round(rng.uniform(0.62, 1.12), 2), "wtadd": rng.choice([0, 0, -100, -200]), "case": rng.choice(CASES)},
            "grid": {"minor": minor, "major": minor * rng.choice([3, 4, 5])},
            "caption": {"size": rng.randint(42, 58), "dy": rng.randint(-40, 40)},
            "post": {"bloom": round(rng.uniform(0.5, 1.1), 2), "bloomThreshold": round(rng.uniform(0.7, 0.95), 2),
                     "vignette": round(rng.uniform(0.25, 0.6), 2), "grain": round(rng.uniform(0.02, 0.09), 3),
                     "ca": round(rng.uniform(0, 1.2), 2), "halation": round(rng.uniform(0, 0.4), 2)},
            "cam2d": {"zoom": round(rng.uniform(0.95, 1.06), 3), "roll": round(rng.uniform(0, 0.02), 4), "hand": round(rng.uniform(0.3, 1.8), 2)},
            "cam3d": {"fov": round(rng.uniform(-8, 12), 1), "roll": round(rng.uniform(-0.06, 0.06), 3), "dist": round(rng.uniform(0.85, 1.2), 2),
                      "hand": round(rng.uniform(0.3, 1.6), 2)},
        }
        cams = _sequence(rng, CAM_MODES, n_scenes, [s["cam"] for s in last.get("scenes", [])])
        revs = _sequence(rng, REVEALS, n_scenes, [s["reveal"] for s in last.get("scenes", [])])
        flrs = _sequence(rng, FLOORS, n_scenes, [s["floor"] for s in last.get("scenes", [])])
        g["scenes"] = [{"cam": c, "reveal": r, "floor": f, "spin": rng.choice([1, -1])} for c, r, f in zip(cams, revs, flrs)]
        if _novel(g, mem):
            return g
    return g
