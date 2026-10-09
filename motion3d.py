"""
Motion 3D engine - high-motion, word-synced 3D diagram explainers (vertical 4K).

Each scene describes a small 3D system diagram (servers, databases, chips, users, ...) plus
"beats": animation actions tied to the exact words the narrator says ("send", "highlight",
"break", "focus", ...). Word timestamps from the TTS turn every cue into a frame-accurate time,
so what moves on screen is always what the voice is talking about.

Rendering: hand-rolled 3D (perspective camera, lit faces, painter's sort) drawn with Skia,
piped straight to ffmpeg. Layout is designed on a 1080x1920 canvas and scaled to the output.
"""
import math
import random
import re
import subprocess
import time

import skia

from explainer_engine import (BASE_W, MONO, MONO_BOLD, SANS_BOLD, SANS_REG, Renderer, clamp, ease, ease_io, ffmpeg_exe)

PALETTE = {
    "blue": (79, 140, 255), "cyan": (34, 211, 238), "purple": (168, 110, 255), "green": (52, 211, 120),
    "orange": (251, 146, 60), "red": (239, 68, 68), "yellow": (250, 204, 21), "pink": (236, 92, 160),
    "white": (215, 220, 230), "grey": (120, 128, 145),
}
TYPE_COLORS = {
    "server": "blue", "db": "purple", "user": "green", "chip": "cyan", "layer": "grey", "box": "blue",
    "sphere": "cyan", "globe": "cyan", "doc": "white", "phone": "white", "laptop": "white", "screen": "blue",
    "cloud": "white", "lock": "yellow", "cubes": "orange", "queue": "orange", "router": "cyan",
}
OBJ_TYPES = tuple(TYPE_COLORS)
BEAT_TYPES = ("show", "hide", "highlight", "send", "flow", "connect", "break", "focus", "reset", "text", "set", "count")

ACCENT = (250, 204, 21)
BG_COLORS = ((6, 7, 12), (10, 12, 22), (5, 6, 10), (40, 70, 140))   # top, middle, bottom, centre glow
DEFAULT_YAW, DEFAULT_PITCH = -24, 54
HOOK_DUR = 1.9   # seconds the opening hook stays on screen

THEMES = [
    {"name": "gold",    "accent": (250, 204, 21), "bg": ((6, 7, 12), (10, 12, 22), (5, 6, 10), (40, 70, 140)), "yaw": -24, "pitch": 54},
    {"name": "cyan",    "accent": (34, 211, 238), "bg": ((5, 9, 14), (8, 16, 26), (4, 7, 11), (20, 90, 130)), "yaw": -30, "pitch": 50},
    {"name": "magenta", "accent": (236, 92, 160), "bg": ((9, 6, 14), (16, 10, 26), (7, 5, 11), (100, 40, 130)), "yaw": -18, "pitch": 57},
    {"name": "lime",    "accent": (163, 230, 53), "bg": ((6, 9, 9), (10, 18, 18), (5, 8, 8), (30, 100, 90)), "yaw": -28, "pitch": 52},
    {"name": "orange",  "accent": (251, 146, 60), "bg": ((10, 7, 7), (20, 12, 12), (8, 5, 5), (120, 60, 40)), "yaw": -20, "pitch": 55},
]


def apply_theme(theme):
    """Variety: switch accent colour, background tint and camera angle for this video."""
    global ACCENT, BG_COLORS, DEFAULT_YAW, DEFAULT_PITCH
    ACCENT, BG_COLORS = tuple(theme["accent"]), tuple(theme["bg"])
    DEFAULT_YAW, DEFAULT_PITCH = theme["yaw"], theme["pitch"]
LIGHT = (0.29, 0.83, -0.46)   # normalised direction towards the light
STAGE_CY = 960
FOCAL = 2100
OBJ_SCALE = 1.3   # objects are drawn a bit chunkier than their 1-unit footprint


def ease_back(x):
    x = clamp(x)
    c1 = 1.70158
    return 1 + (c1 + 1) * (x - 1) ** 3 + c1 * (x - 1) ** 2


def mix(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(len(a)))


def shade(rgb, k):
    return tuple(clamp(c * k, 0, 255) for c in rgb)


def norm_word(w):
    return re.sub(r"[^a-z0-9]", "", w.lower())


# ---------------------------------------------------------------- camera
class Camera:
    """yaw/pitch in degrees, pitch > 0 looks down at the ground plane."""

    def __init__(self, yaw, pitch, dist, tx, ty, tz):
        self.t = (tx, ty, tz)
        self.dist = dist
        y, p = math.radians(yaw), math.radians(pitch)
        self.cy, self.sy, self.cp, self.sp = math.cos(y), math.sin(y), math.cos(p), math.sin(p)
        d = dist * self.cp
        self.pos = (tx - d * self.sy, ty + dist * self.sp, tz - d * self.cy)

    def proj(self, p):
        x, y, z = p[0] - self.t[0], p[1] - self.t[1], p[2] - self.t[2]
        x1 = x * self.cy - z * self.sy
        z1 = x * self.sy + z * self.cy
        y2 = y * self.cp + z1 * self.sp
        d = max(0.4, self.dist + z1 * self.cp - y * self.sp)
        return BASE_W / 2 + FOCAL * x1 / d, STAGE_CY - FOCAL * y2 / d, d


def lerp_cam(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(6))


# ---------------------------------------------------------------- geometry
def box(x0, y0, z0, x1, y1, z1, color, emit=False):
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    faces = [((0, 1, 2, 3), (0, 0, -1)), ((5, 4, 7, 6), (0, 0, 1)), ((4, 0, 3, 7), (-1, 0, 0)),
             ((1, 5, 6, 2), (1, 0, 0)), ((3, 2, 6, 7), (0, 1, 0)), ((4, 5, 1, 0), (0, -1, 0))]
    return [("face", [v[i] for i in idx], n, color, emit) for idx, n in faces]


def cbox(cx, y0, cz, w, h, d, color, emit=False):
    return box(cx - w / 2, y0, cz - d / 2, cx + w / 2, y0 + h, cz + d / 2, color, emit)


def cylinder(cx, y0, cz, r, h, color, n=22, emit=False):
    parts = []
    ring = [(cx + r * math.cos(2 * math.pi * i / n), cz + r * math.sin(2 * math.pi * i / n)) for i in range(n)]
    for i in range(n):
        (xa, za), (xb, zb) = ring[i], ring[(i + 1) % n]
        a = 2 * math.pi * (i + 0.5) / n
        parts.append(("face", [(xa, y0, za), (xb, y0, zb), (xb, y0 + h, zb), (xa, y0 + h, za)],
                      (math.cos(a), 0, math.sin(a)), color, emit))
    parts.append(("face", [(x, y0 + h, z) for x, z in ring], (0, 1, 0), color, emit))
    return parts


def build_parts(typ, color, t, count=4, w=6.0, count_scale=None):
    """Mesh for one object type, base centred at origin. count_scale(i) -> scale of item i (cubes/queue)."""
    P = []
    if typ == "server":
        P += cbox(0, 0, 0, 1.0, 1.7, 1.0, color)
        for i, y in enumerate((0.25, 0.72, 1.19)):
            P += cbox(0, y, -0.52, 0.82, 0.3, 0.04, shade(color, 0.55))
            on = math.sin(t * 5 + i * 2.1) > -0.2
            P += cbox(0.3, y + 0.1, -0.555, 0.08, 0.08, 0.02, PALETTE["green"] if on else (40, 60, 50), emit=on)
            P += cbox(0.15, y + 0.1, -0.555, 0.08, 0.08, 0.02, PALETTE["cyan"], emit=True)
    elif typ == "db":
        P += cylinder(0, 0, 0, 0.62, 1.25, color)
        for y in (0.4, 0.82):
            P += cylinder(0, y, 0, 0.635, 0.05, mix(color, (255, 255, 255), 0.45))
    elif typ == "layer":
        P += cbox(0, 0, 0, w, 0.3, 1.8, color)
        P += cbox(0, 0.3, 0, w - 0.3, 0.03, 1.5, mix(color, (255, 255, 255), 0.12))
    elif typ == "chip":
        P += cbox(0, 0.05, 0, 1.2, 0.2, 1.2, (40, 44, 56))
        P += cbox(0, 0.25, 0, 0.62, 0.05, 0.62, color, emit=True)
        for i in range(4):
            o = -0.42 + i * 0.28
            P += cbox(o, 0, -0.66, 0.1, 0.12, 0.14, (170, 175, 185))
            P += cbox(0.66, 0, o, 0.14, 0.12, 0.1, (170, 175, 185))
    elif typ == "sphere":
        P.append(("sphere", (0, 0.6, 0), 0.6, color))
    elif typ == "globe":
        P.append(("sphere", (0, 0.7, 0), 0.62, shade(color, 0.6)))
        steps = [i * math.pi / 12 for i in range(25)]
        for k in range(3):
            a0 = t * 0.6 + k * math.pi / 3
            pts = [(0.66 * math.cos(u) * math.cos(a0), 0.7 + 0.66 * math.sin(u), 0.66 * math.cos(u) * math.sin(a0)) for u in steps]
            P.append(("line", pts, mix(color, (255, 255, 255), 0.4), 1.6))
        P.append(("line", [(0.66 * math.cos(u), 0.7, 0.66 * math.sin(u)) for u in steps], mix(color, (255, 255, 255), 0.4), 1.6))
    elif typ == "user":
        P += cylinder(0, 0, 0, 0.33, 0.72, color)
        P.append(("sphere", (0, 1.0, 0), 0.26, mix(color, (255, 255, 255), 0.2)))
    elif typ == "doc":
        P += cbox(0, 0, 0, 0.85, 1.15, 0.07, color)
        for i in range(4):
            P += cbox(-0.05 if i == 3 else 0, 0.82 - i * 0.18, -0.045, 0.55 if i < 3 else 0.45, 0.06, 0.02, (90, 100, 120))
    elif typ == "phone":
        P += cbox(0, 0, 0, 0.62, 1.15, 0.09, (40, 44, 56))
        P += cbox(0, 0.08, -0.055, 0.52, 0.98, 0.02, color, emit=True)
    elif typ == "laptop":
        P += cbox(0, 0, 0, 1.4, 0.07, 0.95, (150, 155, 168))
        P += cbox(0, 0.07, 0.44, 1.4, 0.9, 0.06, (60, 64, 76))
        P += cbox(0, 0.13, 0.405, 1.26, 0.76, 0.02, color, emit=True)
    elif typ == "screen":
        P += cbox(0, 0, 0, 0.5, 0.06, 0.4, (90, 95, 110))
        P += cbox(0, 0.06, 0.05, 0.1, 0.35, 0.1, (90, 95, 110))
        P += cbox(0, 0.4, 0, 1.5, 1.0, 0.07, (40, 44, 56))
        P += cbox(0, 0.46, -0.045, 1.38, 0.88, 0.02, shade(color, 0.6), emit=True)
        P += cbox(0, 1.2, -0.06, 1.38, 0.1, 0.02, mix(color, (255, 255, 255), 0.4), emit=True)
    elif typ == "cloud":
        for (x, y, z, r) in ((-0.45, 0.55, 0, 0.42), (0.05, 0.75, 0.05, 0.55), (0.5, 0.5, -0.05, 0.4), (0.05, 0.42, -0.25, 0.38)):
            P.append(("sphere", (x, y, z), r, color))
    elif typ == "lock":
        P += cbox(0, 0, 0, 0.85, 0.65, 0.4, color)
        pts = [(0.27 * math.cos(u), 0.65 + 0.3 * math.sin(u), 0) for u in [i * math.pi / 14 for i in range(15)]]
        P.append(("line", pts, (200, 205, 215), 5.0))
    elif typ == "router":
        P += cbox(0, 0, 0, 1.3, 0.32, 0.85, color)
        for x in (-0.45, 0.45):
            P += cbox(x, 0.32, 0.3, 0.07, 0.6, 0.07, (180, 185, 195))
        for i in range(5):
            on = math.sin(t * 6 + i * 1.3) > 0
            P += cbox(-0.4 + i * 0.2, 0.12, -0.44, 0.08, 0.06, 0.02, PALETTE["green"] if on else (40, 60, 50), emit=on)
    elif typ in ("cubes", "queue"):
        n = max(1, min(int(count), 12))
        for i in range(n):
            s = count_scale(i) if count_scale else 1.0
            if s <= 0.01:
                continue
            if typ == "queue":
                cx, cz = (i - (n - 1) / 2) * 0.48, 0
            else:
                cols = min(4, n)
                cx, cz = (i % cols - (cols - 1) / 2) * 0.46, (i // cols) * 0.46 - 0.23 * ((n - 1) // cols)
            e = 0.36 * s
            P += cbox(cx, 0, cz, e, e, e, color)
    else:  # box
        P += cbox(0, 0, 0, 1.1, 1.1, 1.1, color)
    return P


def obj_height(typ):
    return {"server": 1.7, "db": 1.25, "layer": 0.33, "chip": 0.3, "sphere": 1.2, "globe": 1.35, "user": 1.26,
            "doc": 1.15, "phone": 1.15, "laptop": 1.0, "screen": 1.4, "cloud": 1.3, "lock": 0.95, "router": 0.9,
            "cubes": 0.4, "queue": 0.4}.get(typ, 1.1)


def obj_radius(typ):
    return {"layer": 0.6, "cubes": 1.0, "queue": 1.2, "laptop": 0.8, "screen": 0.8}.get(typ, 0.75)


# ---------------------------------------------------------------- compile storyboard -> timeline
def match_cue(cue, words, start=0):
    """Index of the first word of `cue` in the timed word list, searching from `start`."""
    toks = [norm_word(w) for w in cue.split() if norm_word(w)]
    if not toks:
        return None
    ws = [norm_word(w[0]) for w in words]
    for begin in (start, 0):
        for i in range(begin, len(ws) - len(toks) + 1):
            if ws[i:i + len(toks)] == toks:
                return i
    for i in range(start, len(ws)):  # loose: first word only
        if ws[i] == toks[0]:
            return i
    return None


def auto_camera(objs, yaw=-24, pitch=54, box=(80, 1000, 540, 1420)):
    """Frame the scene: project every object's bounds and adjust distance/target until it fills the stage."""
    if not objs:
        return (yaw, pitch, 16, 0, 0.5, 0)
    pts = []
    for o in objs.values():
        x, z = o["pos"]
        y0 = float(o.get("y", 0))
        hw = float(o.get("w", 6)) / 2 if o["type"] == "layer" else 0.85 * float(o.get("size", 1))
        hd = 0.9 if o["type"] == "layer" else 0.85 * float(o.get("size", 1))
        top = y0 + obj_height(o["type"]) * float(o.get("size", 1)) + 0.25
        for dx in (-hw, hw):
            for dz in (-hd, hd):
                pts += [(x + dx, y0, z + dz), (x + dx, top, z + dz)]
    xs, zs = [p[0] for p in pts], [p[2] for p in pts]
    tx, tz, dist = (min(xs) + max(xs)) / 2, (min(zs) + max(zs)) / 2, 18.0
    bw, bh = box[1] - box[0], box[3] - box[2]
    bcx, bcy = (box[0] + box[1]) / 2, (box[2] + box[3]) / 2
    yr = math.radians(yaw)
    right, fwd = (math.cos(yr), -math.sin(yr)), (math.sin(yr), math.cos(yr))
    sp = math.sin(math.radians(pitch))
    for _ in range(8):
        cam = Camera(yaw, pitch, dist, tx, 0.45, tz)
        pr = [cam.proj(p) for p in pts]
        sx, sy = [q[0] for q in pr], [q[1] for q in pr]
        w, h = max(sx) - min(sx), (max(sy) - min(sy)) + 70   # + room for labels under the bases
        dist = clamp(dist * max(w / (bw * 0.86), h / bh, 0.35), 10, 80)   # 0.86: margin for the camera orbit
        k = FOCAL / dist
        dx = (min(sx) + max(sx)) / 2 - bcx
        dy = (min(sy) + max(sy) + 70) / 2 - bcy
        tx += right[0] * dx / k - fwd[0] * dy / k / sp
        tz += right[1] * dx / k - fwd[1] * dy / k / sp
    return (yaw, pitch, dist, tx, 0.45, tz)


def compile_scenes(scenes, durations, word_times):
    out, t = [], 0.0
    prev_objs, prev_links = {}, {}
    kick_n, last_kick = -1, None
    for sc, dur, words in zip(scenes, durations, word_times):
        if sc.get("kicker") != last_kick:
            kick_n += 1
            last_kick = sc.get("kicker")
        objs = {}
        for o in sc.get("objects", []):
            o = dict(o)
            o.setdefault("color", TYPE_COLORS.get(o["type"], "blue"))
            o["size"] = OBJ_SCALE * clamp(float(o.get("size", 1.0)), 0.5, 2.0)
            o["rgb"] = PALETTE.get(o["color"], PALETTE["blue"])
            objs[o["id"]] = o
        # anything standing on a layer (platform) sits on top of it
        for L in [o for o in objs.values() if o["type"] == "layer"]:
            half_w = float(L.get("w", 6)) * L["size"] / 2
            for o in objs.values():
                if o["type"] != "layer" and abs(o["pos"][0] - L["pos"][0]) <= half_w and abs(o["pos"][1] - L["pos"][1]) <= 1.25:
                    o["y"] = max(float(o.get("y", 0)), 0.33 * L["size"])
        # beats -> times (the moment their cue words are spoken)
        beats, ptr = [], 0
        raw = sc.get("beats", [])
        for bi, b in enumerate(raw):
            idx = match_cue(b.get("cue", ""), words, ptr)
            if idx is None:
                tb = dur * (bi + 1) / (len(raw) + 1)
            else:
                tb = max(0.0, words[idx][1] - 0.08)
                ptr = idx
            beats.append({**b, "t": tb})
        beats.sort(key=lambda b: b["t"])
        order = list(objs)
        for oid, o in objs.items():
            shows = [b["t"] for b in beats if b["do"] == "show" and oid in b.get("ids", [])]
            o["carried"] = oid in prev_objs and prev_objs[oid]["type"] == o["type"] and not shows
            o["appear"] = 0.0 if o["carried"] else (shows[0] if shows else 0.05 + 0.1 * order.index(oid))
            o["prev_pos"] = prev_objs[oid]["pos"] if o["carried"] else o["pos"]
            o["prev_y"] = prev_objs[oid].get("y", 0) if o["carried"] else o.get("y", 0)
            o["hide"] = next((b["t"] for b in beats if b["do"] == "hide" and oid in b.get("ids", [])), None)
            o["hl"] = [b["t"] for b in beats if b["do"] == "highlight" and oid in b.get("ids", [])]
            o["brk"] = next((b["t"] for b in beats if b["do"] == "break" and oid in b.get("ids", [])), None)
            o["sets"] = [(b["t"], b) for b in beats if b["do"] == "set" and b.get("id") == oid]
            o["counts"] = [(b["t"], int(b.get("n", 1))) for b in beats if b["do"] == "count" and b.get("id") == oid]
            o["arrivals"] = [b["t"] + 0.95 for b in beats if b["do"] == "send" and b.get("to") == oid]
        links = {}
        for l in sc.get("links", []):
            if l.get("from") in objs and l.get("to") in objs:
                key = f'{l["from"]}>{l["to"]}'
                carried = key in prev_links
                start = 0.0 if carried else max(objs[l["from"]]["appear"], objs[l["to"]]["appear"]) + 0.25
                links[key] = {**l, "carried": carried, "appear": start}
        for b in beats:
            if b["do"] in ("connect", "flow") and b.get("from") in objs and b.get("to") in objs:
                key = f'{b["from"]}>{b["to"]}'
                if key not in links:
                    links[key] = {"from": b["from"], "to": b["to"], "label": b.get("label", "") if b["do"] == "connect" else "",
                                  "carried": False, "appear": b["t"]}
        c = sc.get("camera") if isinstance(sc.get("camera"), dict) else {}
        cam = auto_camera(objs, yaw=float(c.get("yaw", DEFAULT_YAW)), pitch=float(c.get("pitch", DEFAULT_PITCH)))
        if c.get("zoom"):
            cam = cam[:2] + (cam[2] / clamp(float(c["zoom"]), 0.5, 2.0),) + cam[3:]
        # captions: chunks of <= 4 words, split on pauses
        chunks, cur = [], []
        for w in words:
            if cur and (len(cur) >= 4 or w[1] - cur[-1][2] > 0.22):
                chunks.append(cur)
                cur = []
            cur.append(w)
        if cur:
            chunks.append(cur)
        out.append({"start": t, "dur": dur, "kicker": sc.get("kicker", ""), "chapter": kick_n, "title": sc.get("title", ""),
                    "objs": objs, "links": links, "beats": beats, "cam": cam, "chunks": chunks,
                    "prev_objs": prev_objs, "prev_links": prev_links})
        prev_objs, prev_links = objs, links
        t += dur
    for sc in out:
        sc["chapters"] = kick_n + 1
    return out, t


# ---------------------------------------------------------------- renderer
class MotionRenderer(Renderer):
    def __init__(self, width=2160, height=3840, fps=30, handle=""):
        super().__init__(width, height, fps, handle)
        self.bg = self._make_background()
        rng = random.Random(7)
        self.dust = [(rng.uniform(-9, 9), rng.uniform(0, 5), rng.uniform(-7, 7), rng.uniform(0.6, 1.8)) for _ in range(70)]
        self.end_cams = {}
        self.focus_cams = {}
        self.vignette = self._make_vignette()
        self.hook = ""
        self.series_label = ""

    def _make_background(self):
        surf = skia.Surface(self.w, self.h)
        c = surf.getCanvas()
        k = self.k
        c.drawPaint(skia.Paint(Shader=skia.GradientShader.MakeLinear(
            [skia.Point(0, 0), skia.Point(0, self.h)], [skia.Color(*BG_COLORS[0]), skia.Color(*BG_COLORS[1]), skia.Color(*BG_COLORS[2])])))
        c.drawPaint(skia.Paint(Shader=skia.GradientShader.MakeRadial(
            skia.Point(540 * k, STAGE_CY * k), 720 * k, [skia.Color(*BG_COLORS[3], 70), skia.Color(0, 0, 0, 0)])))
        return surf.makeImageSnapshot()

    def _make_vignette(self):
        surf = skia.Surface(self.w, self.h)
        c = surf.getCanvas()
        c.clear(skia.ColorTRANSPARENT)
        k = self.k
        c.drawPaint(skia.Paint(Shader=skia.GradientShader.MakeRadial(
            skia.Point(540 * k, 900 * k), 1250 * k, [skia.Color(0, 0, 0, 0), skia.Color(0, 0, 0, 0), skia.Color(0, 0, 0, 170)],
            [0, 0.55, 1])))
        return surf.makeImageSnapshot()

    # --- drawing helpers
    def floor_ring(self, cam, x, y, z, r, rgb, a, width=2.0, dash=None, phase=0.0, n=40):
        if a <= 0.01 or r <= 0:
            return
        pts = []
        for i in range(n + 1):
            u = 2 * math.pi * i / n
            q = cam.proj((x + r * math.cos(u), y + 0.02, z + r * math.sin(u)))
            pts.append((q[0], q[1]))
        self.polyline(pts, rgb, a, width, dash=dash, phase=phase)

    def beam(self, cam, x, y, z, h, rgb, a):
        """Soft vertical light column rising from the floor."""
        if a <= 0.01:
            return
        b, t = cam.proj((x, y, z)), cam.proj((x, y + h, z))
        w = 0.55 * FOCAL / b[2]
        k = self.k
        paint = skia.Paint(AntiAlias=True, Shader=skia.GradientShader.MakeLinear(
            [skia.Point(b[0] * k, b[1] * k), skia.Point(t[0] * k, t[1] * k)], [self.color(rgb, a), self.color(rgb, 0)]))
        path = skia.Path()
        for i, (px, py) in enumerate([(b[0] - w, b[1]), (t[0] - w * 0.6, t[1]), (t[0] + w * 0.6, t[1]), (b[0] + w, b[1])]):
            if i == 0:
                path.moveTo(px * k, py * k)
            else:
                path.lineTo(px * k, py * k)
        path.close()
        self.c.drawPath(path, paint)

    def glow(self, x, y, r, rgb, a, squash=1.0):
        if a <= 0.01 or r <= 0:
            return
        k = self.k
        p = skia.Paint(AntiAlias=True, Shader=skia.GradientShader.MakeRadial(
            skia.Point(0, 0), r * k, [self.color(rgb, a), self.color(rgb, a * 0.35), self.color(rgb, 0)], [0, 0.4, 1]))
        self.c.save()
        self.c.translate(x * k, y * k)
        self.c.scale(1, squash)
        self.c.drawCircle(0, 0, r * k, p)
        self.c.restore()

    def poly(self, pts, fill, a, edge=None, edge_a=0.0):
        k = self.k
        path = skia.Path()
        path.moveTo(pts[0][0] * k, pts[0][1] * k)
        for p in pts[1:]:
            path.lineTo(p[0] * k, p[1] * k)
        path.close()
        self.c.drawPath(path, self.fill_paint(fill, a))
        if edge is not None and edge_a > 0:
            self.c.drawPath(path, self.stroke_paint(edge, edge_a, 1.1))

    def polyline(self, pts, rgb, a, width, dash=None, phase=0.0):
        if len(pts) < 2 or a <= 0.01:
            return
        k = self.k
        path = skia.Path()
        path.moveTo(pts[0][0] * k, pts[0][1] * k)
        for p in pts[1:]:
            path.lineTo(p[0] * k, p[1] * k)
        paint = self.stroke_paint(rgb, a, width)
        if dash:
            paint.setPathEffect(skia.DashPathEffect.Make([d * k for d in dash], phase * k))
        self.c.drawPath(path, paint)

    def sphere(self, x, y, r, rgb, a):
        if a <= 0.01:
            return
        k = self.k
        hi, lo = mix(rgb, (255, 255, 255), 0.55), shade(rgb, 0.35)
        p = skia.Paint(AntiAlias=True, Shader=skia.GradientShader.MakeRadial(
            skia.Point((x - r * 0.35) * k, (y - r * 0.4) * k), r * 1.45 * k,
            [self.color(hi, a), self.color(rgb, a), self.color(lo, a)], [0, 0.45, 1]))
        self.c.drawCircle(x * k, y * k, r * k, p)

    # --- scene state
    def cam_at(self, sc_i, tl, scenes):
        sc = scenes[sc_i]
        val = self.end_cams.get(sc_i - 1, sc["cam"]) if sc_i > 0 else sc["cam"]
        goal, seg_start, seg_dur = sc["cam"], 0.0, 1.1
        for bi, b in enumerate(sc["beats"]):
            if b["do"] not in ("focus", "reset") or b["t"] > tl:
                continue
            val = lerp_cam(val, goal, ease_io((b["t"] - seg_start) / seg_dur))
            if b["do"] == "focus":
                key = (sc_i, bi)
                if key not in self.focus_cams:
                    sub = {i: sc["objs"][i] for i in b.get("ids", []) if i in sc["objs"]}
                    fc = auto_camera(sub, yaw=sc["cam"][0] + 10, pitch=sc["cam"][1] - 6) if sub else sc["cam"]
                    self.focus_cams[key] = fc[:2] + (max(fc[2], sc["cam"][2] * 0.55),) + fc[3:]
                goal = self.focus_cams[key]
            else:
                goal = sc["cam"]
            seg_start, seg_dur = b["t"], 0.9
        return lerp_cam(val, goal, ease_io((tl - seg_start) / seg_dur))

    def obj_state(self, o, tl):
        if tl < o["appear"]:
            return None
        if o["carried"]:
            s, a = 1.0, 1.0
            m = ease_io(tl / 0.8)
            pos = mix(o["prev_pos"], o["pos"], m)
            y = o["prev_y"] + (o.get("y", 0) - o["prev_y"]) * m
        else:
            x = (tl - o["appear"]) / 0.55
            s, a = ease_back(x), ease(x / 0.5)
            pos, y = o["pos"], o.get("y", 0) + (1 - ease(x)) * 0.8   # drops in from above
        if o["hide"] is not None and tl >= o["hide"]:
            x = ease((tl - o["hide"]) / 0.4)
            s, a = s * (1 - x), a * (1 - x)
            if a <= 0.01:
                return None
        h = max([ease((tl - ht) / 0.35) for ht in o["hl"] if tl >= ht] + [0])
        b = ease((tl - o["brk"]) / 0.3) if o["brk"] is not None and tl >= o["brk"] else 0
        bump = sum(math.exp(-(tl - ta) * 7) * 0.12 for ta in o["arrivals"] if tl >= ta)
        label, sub, color = o.get("label", ""), o.get("sub", ""), o["rgb"]
        for ts, st in o["sets"]:
            if tl >= ts:
                label = st.get("label", label)
                sub = st.get("sub", sub)
                if st.get("color") in PALETTE:
                    color = PALETTE[st["color"]]
        count = int(o.get("count", 4))
        count_times = [o["appear"] + 0.06 * i for i in range(count)]
        for tc, n in o["counts"]:
            if tc <= tl:
                count_times += [tc + 0.09 * j for j in range(max(0, n - len(count_times)))]
                count = max(count, n)
        return {"o": o, "pos": pos, "y": y, "s": s, "a": a, "h": h, "b": b, "bump": bump, "label": label, "sub": sub,
                "rgb": color, "count": count, "count_times": count_times, "tl": tl}

    def outgoing_state(self, o, tl):
        x = ease(tl / 0.45)
        if x >= 1:
            return None
        return {"o": o, "pos": o["pos"], "y": o.get("y", 0), "s": 1 - x, "a": 1 - x, "h": 0, "b": 0, "bump": 0,
                "label": o.get("label", ""), "sub": o.get("sub", ""), "rgb": o["rgb"], "count": int(o.get("count", 4)),
                "count_times": [-1] * 12, "tl": 99}

    # --- 3D drawing
    def draw_grid(self, cam, T):
        tx, tz = round(cam.t[0]), round(cam.t[2])
        for i in range(-11, 12):
            for horiz in (0, 1):
                for j in range(-11, 12, 2):
                    if horiz:
                        p0, p1 = (tx + j, 0, tz + i), (tx + j + 2, 0, tz + i)
                    else:
                        p0, p1 = (tx + i, 0, tz + j), (tx + i, 0, tz + j + 2)
                    mx, mz = (p0[0] + p1[0]) / 2 - cam.t[0], (p0[2] + p1[2]) / 2 - cam.t[2]
                    fade = clamp(1 - math.hypot(mx, mz) / 11)
                    if fade <= 0.02:
                        continue
                    a, b = cam.proj(p0), cam.proj(p1)
                    if a[2] < 1 or b[2] < 1:
                        continue
                    self.line(a[0], a[1], b[0], b[1], (90, 120, 200), 0.16 * fade * fade, 1.0)
        for i in range(-4, 5):
            for j in range(-4, 5):
                p = cam.proj((tx + i, 0, tz + j))
                tw = 0.5 + 0.5 * math.sin(T * 1.7 + i * 1.3 + j * 0.7)
                self.circle(p[0], p[1], 1.6, fill=(120, 160, 255), a=0.25 * tw * clamp(1 - math.hypot(i, j) / 6))

    def draw_dust(self, cam, T):
        for (x, y, z, sp) in self.dust:
            yy = (y + T * 0.12 * sp) % 5
            p = cam.proj((x + math.sin(T * 0.3 + z) * 0.3, yy, z))
            if p[2] < 1:
                continue
            self.circle(p[0], p[1], clamp(40 / p[2], 0.6, 3.5), fill=(160, 190, 255), a=0.22 * math.sin(math.pi * yy / 5))

    def object_items(self, st, cam, T, mirror=False):
        """Projected, depth-sorted draw items for one object (mirror=True: its reflection in the floor)."""
        o = st["o"]
        typ, s = o["type"], max(0.0, st["s"]) * (1 + st["bump"]) * float(o.get("size", 1.0))
        rgb = mix(st["rgb"], PALETTE["red"], st["b"])
        rgb = mix(rgb, mix(rgb, (255, 255, 255), 0.35), st["h"] * 0.6)
        px, pz = st["pos"]
        ox, oz = px + math.sin(T * 55) * 0.05 * st["b"], pz
        lift = st["y"] + st["h"] * (0.25 + 0.06 * math.sin(T * 3))
        tl = st["tl"]
        m = -1 if mirror else 1

        def count_scale(i):
            if i >= len(st["count_times"]):
                return 0.0
            return ease_back((tl - st["count_times"][i]) / 0.35) if st["count_times"][i] >= 0 else 1.0

        parts = build_parts(typ, rgb, T, count=st["count"], w=float(o.get("w", 6)), count_scale=count_scale)
        items = []
        for p in parts:
            if p[0] == "face":
                _, verts, n, col, emit = p
                wv = [(ox + v[0] * s, m * (lift + v[1] * s), oz + v[2] * s) for v in verts]
                c = [sum(v[i] for v in wv) / len(wv) for i in range(3)]
                if n[0] * (cam.pos[0] - c[0]) + m * n[1] * (cam.pos[1] - c[1]) + n[2] * (cam.pos[2] - c[2]) <= 0:
                    continue
                pr = [cam.proj(v) for v in wv]
                depth = sum(q[2] for q in pr) / len(pr)
                if emit:
                    fill = col
                else:
                    fill = shade(col, 0.22 + 0.78 * max(0.0, n[0] * LIGHT[0] + n[1] * LIGHT[1] + n[2] * LIGHT[2]))
                items.append((depth, "poly", [(q[0], q[1]) for q in pr], fill, mix(col, (255, 255, 255), 0.5)))
            elif p[0] == "sphere":
                _, cen, r, col = p
                q = cam.proj((ox + cen[0] * s, m * (lift + cen[1] * s), oz + cen[2] * s))
                items.append((q[2], "sphere", (q[0], q[1]), r * s * FOCAL / q[2], col))
            elif p[0] == "line":
                _, pts, col, wdt = p
                pr = [cam.proj((ox + v[0] * s, m * (lift + v[1] * s), oz + v[2] * s)) for v in pts]
                items.append((sum(q[2] for q in pr) / len(pr) - 0.01, "line", [(q[0], q[1]) for q in pr], col, wdt))
        items.sort(key=lambda it: -it[0])
        return items

    def draw_reflection(self, st, cam, T):
        if st["a"] <= 0.01 or st["o"]["type"] == "layer" or st["y"] > 0.05:
            return
        for it in self.object_items(st, cam, T, mirror=True):
            if it[1] == "poly":
                self.poly(it[2], it[3], 0.13 * st["a"])
            elif it[1] == "sphere":
                self.sphere(it[2][0], it[2][1], it[3], it[4], 0.13 * st["a"])

    def draw_floor_fx(self, st, cam, T):
        """Shockwave when an object lands or a packet arrives; spinning ring + light beam while highlighted."""
        o, a = st["o"], st["a"]
        x, z, y = st["pos"][0], st["pos"][1], st["y"]
        size = o["size"]
        tl = st["tl"]
        if not o.get("carried") and 0 <= tl - o["appear"] < 0.8:
            u = (tl - o["appear"]) / 0.8
            self.floor_ring(cam, x, y, z, size * (0.5 + 1.6 * ease(u)), st["rgb"], 0.7 * (1 - u), 3.0)
        for ta in o.get("arrivals", []):
            if 0 <= tl - ta < 0.7:
                u = (tl - ta) / 0.7
                self.floor_ring(cam, x, y, z, size * (0.6 + 1.4 * ease(u)), (255, 255, 255), 0.6 * (1 - u), 2.5)
        if st["h"] > 0.01:
            self.floor_ring(cam, x, y, z, 1.05 * size, st["rgb"], 0.85 * st["h"] * a, 3.0, dash=(18, 12), phase=-T * 60)
            self.beam(cam, x, y, z, 3.2 * size, st["rgb"], 0.16 * st["h"] * a)

    def draw_object(self, st, cam, T):
        a = st["a"]
        if a <= 0.01:
            return
        base = cam.proj((st["pos"][0], st["y"], st["pos"][1]))
        scale = FOCAL / base[2]
        self.glow(base[0], base[1], 0.95 * scale * st["s"], (0, 0, 0), 0.55 * a, squash=0.42)
        if st["h"] > 0:
            self.glow(base[0], base[1], 1.5 * scale, st["rgb"], 0.45 * st["h"] * a, squash=0.45)
        if st["b"] > 0:
            self.glow(base[0], base[1] - 0.6 * scale, 1.4 * scale, PALETTE["red"], 0.35 * st["b"] * a)
        for it in self.object_items(st, cam, T):
            if it[1] == "poly":
                self.poly(it[2], it[3], a, it[4], 0.35 * a)
            elif it[1] == "sphere":
                self.sphere(it[2][0], it[2][1], it[3], it[4], a)
            else:
                self.polyline(it[2], it[3], a, it[4])

    def draw_label(self, st, cam):
        o, a = st["o"], st["a"]
        if a <= 0.02 or not st["label"]:
            return
        base = cam.proj((st["pos"][0], st["y"], st["pos"][1] - (0.95 if o["type"] == "layer" else 0.6 * o["size"])))
        y = base[1] + 24
        size = self.fit_size(st["label"], SANS_BOLD, 25, 240)
        w = self.text_width(st["label"], SANS_BOLD, size) + 26
        self.rrect(base[0] - w / 2, y - size - 3, w, size + 15, 9, fill=(14, 16, 26), a=0.8 * a,
                   edge=mix(st["rgb"], (255, 255, 255), 0.3) if st["h"] > 0.3 else (60, 66, 84), edge_a=0.9 * a)
        self.text(st["label"], base[0], y + 3, SANS_BOLD, size, (240, 242, 248), a, "center")
        if st["sub"]:
            self.text(st["sub"], base[0], y + 31, MONO, self.fit_size(st["sub"], MONO, 17, 260), (150, 160, 185), a, "center")
        if st["b"] > 0.5:
            top = cam.proj((st["pos"][0], st["y"] + obj_height(o["type"]) * o["size"] + 0.5, st["pos"][1]))
            self.pill("CRASHED", top[0], top[1], st["b"] * a, font=SANS_BOLD, size=20, active=True)

    def link_points(self, l, states):
        A, B = states.get(l["from"]), states.get(l["to"])
        if not A or not B:
            return None
        ax, az = A["pos"]
        bx, bz = B["pos"]
        dx, dz = bx - ax, bz - az
        L = math.hypot(dx, dz) or 1
        ra, rb = obj_radius(A["o"]["type"]) * A["o"]["size"], obj_radius(B["o"]["type"]) * B["o"]["size"]
        if A["o"]["type"] == "layer" or B["o"]["type"] == "layer":
            ra = rb = 0.35
        p0 = (ax + dx / L * ra, A["y"] + 0.04, az + dz / L * ra)
        p1 = (bx - dx / L * rb, B["y"] + 0.04, bz - dz / L * rb)
        return p0, p1, min(A["a"], B["a"])

    def draw_link(self, l, states, cam, tl, T, prog_override=None):
        lp = self.link_points(l, states)
        if not lp:
            return
        p0, p1, a = lp
        prog = prog_override if prog_override is not None else (1.0 if l["carried"] else ease((tl - l["appear"]) / 0.6))
        if prog <= 0:
            return
        pe = tuple(p0[i] + (p1[i] - p0[i]) * prog for i in range(3))
        q0, q1 = cam.proj(p0), cam.proj(pe)
        self.line(q0[0], q0[1], q1[0], q1[1], (110, 150, 255), 0.25 * a, 5.0)
        self.polyline([(q0[0], q0[1]), (q1[0], q1[1])], (170, 200, 255), 0.9 * a, 2.2, dash=(10, 9), phase=-T * 40)
        if prog >= 0.99:
            ang = math.atan2(q1[1] - q0[1], q1[0] - q0[0])
            tip = (q1[0], q1[1])
            pts = [tip, (tip[0] - 16 * math.cos(ang - 0.45), tip[1] - 16 * math.sin(ang - 0.45)),
                   (tip[0] - 16 * math.cos(ang + 0.45), tip[1] - 16 * math.sin(ang + 0.45))]
            self.poly(pts, (190, 210, 255), 0.9 * a)
            u = (T * 0.6 + (len(l["from"]) * 7 + len(l["to"]) * 3) % 10 / 10) % 1.0
            q = cam.proj(tuple(p0[i] + (p1[i] - p0[i]) * u for i in range(3)))
            self.glow(q[0], q[1], 22, (150, 190, 255), 0.55 * a * math.sin(math.pi * u))
            if l.get("label"):
                m = cam.proj(tuple((p0[i] + p1[i]) / 2 for i in range(3)))
                self.pill(l["label"], m[0], m[1] - 22, a * 0.95, font=MONO, size=17)

    def packet(self, p0, p1, u, cam, rgb, label, a=1.0, arc=1.3):
        mid = ((p0[0] + p1[0]) / 2, max(p0[1], p1[1]) + arc, (p0[2] + p1[2]) / 2)

        def at(v):
            return tuple((1 - v) ** 2 * p0[i] + 2 * (1 - v) * v * mid[i] + v * v * p1[i] for i in range(3))
        for k in range(13, -1, -1):
            v = u - k * 0.022
            if v < 0 or v > 1:
                continue
            q = cam.proj(at(v))
            r = 190 / q[2] * (1 - k * 0.06)
            if k:
                self.circle(q[0], q[1], r * 0.8, fill=rgb, a=0.35 * a * (1 - k / 14))
            self.glow(q[0], q[1], r * 3.2, rgb, 0.16 * a * (1 - k / 14))
            if k == 0:
                self.circle(q[0], q[1], r, fill=mix(rgb, (255, 255, 255), 0.6), a=a)
                if label:
                    self.pill(label, q[0], q[1] - r - 30, a, font=MONO_BOLD, size=19)

    def draw_callout(self, text, x, a, rgb):
        if a <= 0.01:
            return
        s = 0.9 + 0.1 * ease_back(x)
        size = self.fit_size(text, SANS_BOLD, 44, 850, 0.5)
        w = self.text_width(text, SANS_BOLD, size) + 96
        cy = 478
        k = self.k
        self.c.save()
        self.c.translate(540 * k, cy * k)
        self.c.scale(s, s)
        self.c.translate(-540 * k, -cy * k)
        self.glow(540, cy, w * 0.6, rgb, 0.2 * a, squash=0.35)
        x0 = 540 - w / 2
        self.rrect(x0, cy - 44, w, 88, 18, fill=(14, 18, 32), a=0.94 * a, edge=mix(rgb, (0, 0, 0), 0.3), edge_a=0.8 * a, edge_w=1.5)
        self.rrect(x0, cy - 44, 10, 88, 5, fill=rgb, a=a)
        self.pill("KEY IDEA", 540, cy - 52, a, font=MONO_BOLD, size=15, active=True)
        reveal = ease_io(clamp(x * 1.6 - 0.15))
        self.c.save()
        self.c.clipRect(skia.Rect.MakeLTRB((x0 + 20) * k, (cy - 44) * k, (x0 + 20 + (w - 20) * reveal) * k, (cy + 44) * k))
        self.text(text, 545, cy + size * 0.36, SANS_BOLD, size, (245, 246, 250), a, "center")
        self.c.restore()
        if reveal < 1:
            cx = x0 + 20 + (w - 20) * reveal
            self.rrect(cx - 2, cy - 30, 4, 60, 2, fill=rgb, a=a)
        self.c.restore()

    def draw_captions(self, sc, tl):
        chunks = sc["chunks"]
        cur = None
        for ci, ch in enumerate(chunks):
            end = chunks[ci + 1][0][1] if ci + 1 < len(chunks) else ch[-1][2] + 0.4
            if ch[0][1] - 0.05 <= tl < end:
                cur = ch
                break
        if not cur:
            return
        pop = ease_back((tl - cur[0][1] + 0.05) / 0.18)
        size, space, y = 56, 16, 1640
        widths = [self.text_width(w[0], SANS_BOLD, size) for w in cur]
        total = sum(widths) + space * (len(cur) - 1)
        scale = min(1.0, 980 / total) * (0.92 + 0.08 * pop)
        k = self.k
        self.c.save()
        self.c.translate(540 * k, y * k)
        self.c.scale(scale, scale)
        self.c.translate(-540 * k, -y * k)
        x = 540 - total / 2
        for wi, ((wd, s0, s1), w) in enumerate(zip(cur, widths)):
            nxt = cur[wi + 1][1] if wi + 1 < len(cur) else max(s1, s0 + 0.25) + 0.15
            active = s0 - 0.03 <= tl < nxt - 0.03
            if active:
                self.rrect(x - 10, y - size - 2, w + 20, size + 22, 12, fill=ACCENT, a=0.95)
            col = (15, 15, 20) if active else ((255, 255, 255) if tl >= s0 else (175, 180, 195))
            self.text(wd, x, y + 4, SANS_BOLD, size, col, 1.0)
            x += w + space
        self.c.restore()

    # --- header / HUD
    def draw_header(self, sc, prev, tl, t):
        e = ease(tl / 0.5) if prev else ease(tl / 0.6)
        # segmented chapter progress across the top
        n, ch = sc["chapters"], sc["chapter"]
        gap, x0, w_all = 8, 90, 900
        seg = (w_all - gap * (n - 1)) / n
        for i in range(n):
            x = x0 + i * (seg + gap)
            self.rrect(x, 112, seg, 6, 3, fill=(60, 66, 90), a=0.7)
            if i < ch:
                self.rrect(x, 112, seg, 6, 3, fill=ACCENT, a=0.95)
            elif i == ch:
                self.rrect(x, 112, seg * clamp(tl / sc["dur"]), 6, 3, fill=ACCENT, a=0.95)
        # chapter chip + section name
        new_chapter = prev is None or prev["chapter"] != ch
        ka = e if new_chapter else 1.0
        if prev and new_chapter and e < 1:
            self.text(f"CHAPTER {prev['chapter'] + 1:02d}", 540, 214 - 14 * e, MONO_BOLD, 18, ACCENT, 1 - e, "center")
            self.text(prev["kicker"].upper(), 540, 246 - 14 * e, MONO, 20, (140, 150, 180), 1 - e, "center")
        self.text(f"CHAPTER {ch + 1:02d} / {n:02d}", 540, 214 + 14 * (1 - ka), MONO_BOLD, 18, ACCENT, ka, "center")
        self.text(sc["kicker"].upper(), 540, 246 + 14 * (1 - ka), MONO, 20, (140, 150, 180), ka, "center")
        # title: words rise in one after another
        if prev and e < 1:
            self.text(prev["title"], 540, 318 - 16 * e, SANS_BOLD, self.fit_size(prev["title"], SANS_BOLD, 54, 960, 0.6),
                      (245, 246, 250), 1 - e, "center", blur=e * 6)
        size = self.fit_size(sc["title"], SANS_BOLD, 54, 960, 0.6)
        words = sc["title"].split()
        widths = [self.text_width(w, SANS_BOLD, size) for w in words]
        space = size * 0.28
        x = 540 - (sum(widths) + space * (len(words) - 1)) / 2
        for i, (w, wd) in enumerate(zip(words, widths)):
            u = ease_back((tl - 0.12 - i * 0.07) / 0.45)
            a = ease((tl - 0.12 - i * 0.07) / 0.3)
            self.text(w, x, 318 + 26 * (1 - u), SANS_BOLD, size, (245, 246, 250), a)
            x += wd + space
        self.rrect(540 - 46 * e, 352, 92 * e, 5, 2.5, fill=ACCENT, a=0.95 * e)

    def draw_end_card(self, t, total):
        u = (t - (total - 2.7)) / 0.6
        if u <= 0:
            return
        a = ease(u)
        self.c.drawRect(skia.Rect.MakeWH(self.w, self.h), self.fill_paint((5, 6, 12), 0.88 * a))
        cy = 900
        r = 92 * (0.85 + 0.15 * ease_back(u))
        self.glow(540, cy, 260, ACCENT, 0.25 * a)
        self.circle(540, cy, r, fill=(16, 18, 30), a=a, edge=ACCENT, edge_a=a, edge_w=5)
        k = self.k
        arc = skia.Rect.MakeXYWH((540 - r - 16) * k, (cy - r - 16) * k, (2 * r + 32) * k, (2 * r + 32) * k)
        self.c.drawArc(arc, (t * 135) % 360, 120, False, self.stroke_paint(ACCENT, 0.8 * a, 4))
        initial = (self.handle.lstrip("@")[:1] or "D").upper()
        self.text(initial, 540, cy + 34, SANS_BOLD, 96, (250, 250, 252), a, "center")
        self.text(self.handle or "", 540, cy + 175, SANS_BOLD, 52, (245, 246, 250), ease(u - 0.2), "center")
        self.text("A new 3D explainer every day", 540, cy + 225, SANS_REG, 30, (160, 170, 195), ease(u - 0.35), "center")
        b = ease_back(u - 0.5)
        if b > 0:
            w = 300 * (1 + 0.04 * math.sin(t * 6)) * b
            self.rrect(540 - w / 2, cy + 280, w, 84, 42, fill=ACCENT, a=a)
            self.text("FOLLOW", 540, cy + 335, SANS_BOLD, 36, (15, 15, 20), a * clamp(b), "center")

    def draw_hook(self, t):
        """Giant kinetic hook text over the opening second - stops the scroll."""
        if not self.hook or t >= HOOK_DUR:
            return
        out = ease((t - (HOOK_DUR - 0.35)) / 0.35)
        a = 1 - out
        self.c.drawRect(skia.Rect.MakeWH(self.w, self.h), self.fill_paint((4, 5, 9), 0.62 * a))
        parts, bold = [], False
        for chunk in self.hook.split("**"):
            for w in chunk.split():
                parts.append((w, bold))
            bold = not bold
        size = 92
        while True:
            lines, cur, cur_w = [], [], 0
            for w, b in parts:
                ww = self.text_width(w, SANS_BOLD, size)
                sp = size * 0.28 if cur else 0
                if cur and cur_w + sp + ww > 940:
                    lines.append(cur)
                    cur, cur_w, sp = [], 0, 0
                cur.append((w, b, ww))
                cur_w += sp + ww
            lines.append(cur)
            if len(lines) <= 3 or size <= 56:
                break
            size -= 6
        punch = 1.18 - 0.18 * ease_back(t / 0.32)
        k = self.k
        cy = 820
        self.c.save()
        self.c.translate(540 * k, cy * k)
        self.c.scale(punch, punch)
        self.c.translate(-540 * k, -cy * k)
        lh = size * 1.18
        y0 = cy - lh * (len(lines) - 1) / 2 + size * 0.35
        wi = 0
        for li, line in enumerate(lines):
            total = sum(w for _, _, w in line) + size * 0.28 * (len(line) - 1)
            x = 540 - total / 2
            for w, b, ww in line:
                appear = ease((t - 0.05 - wi * 0.06) / 0.18)
                yy = y0 + li * lh + 30 * (1 - appear)
                if b:
                    sweep = ease((t - 0.25) / 0.35)
                    if sweep > 0:
                        self.rrect(x - 10, yy - size * 0.92, (ww + 20) * sweep, size * 1.15, 14, fill=ACCENT, a=0.95 * a)
                self.text(w, x, yy, SANS_BOLD, size, (15, 15, 20) if b and ease((t - 0.25) / 0.35) > 0.5 else (250, 250, 252),
                          a * appear)
                x += ww + size * 0.28
                wi += 1
        self.c.restore()
        if t < 0.14:
            self.c.drawRect(skia.Rect.MakeWH(self.w, self.h), self.fill_paint((255, 255, 255), 0.55 * (1 - t / 0.14)))

    def draw_series_chip(self, a):
        if self.series_label and a > 0.01:
            w = self.pill_width(self.series_label, MONO_BOLD, 17)
            self.pill(self.series_label, 90 + w / 2, 160, a, font=MONO_BOLD, size=17)

    def draw_sparks(self, cam, x, y, z, u, rgb):
        if not 0 <= u < 1:
            return
        c = cam.proj((x, y, z))
        sc_ = FOCAL / c[2]
        for i in range(12):
            ang = i * math.pi / 6 + 0.3
            d = (0.3 + 1.5 * ease(u)) * sc_ * 0.55
            px, py = c[0] + math.cos(ang) * d, c[1] + math.sin(ang) * d * 0.7 - 30 * u
            self.circle(px, py, 4.5 * (1 - u) + 1, fill=mix(rgb, (255, 255, 255), 0.5), a=1 - u)
        self.glow(c[0], c[1], 90 * (1 - u) + 20, rgb, 0.5 * (1 - u))

    # --- frame
    def frame3d(self, scenes, t, total):
        self.c.drawImage(self.bg, 0, 0)
        si = 0
        for i, sc in enumerate(scenes):
            if t >= sc["start"]:
                si = i
        sc = scenes[si]
        tl = t - sc["start"]
        prev = scenes[si - 1] if si > 0 else None

        cv = self.cam_at(si, tl, scenes)
        orbit = 7 * math.sin(t * 0.23) + 3 * math.sin(t * 0.61)
        swing = (12 if si % 2 else -12) * (1 - ease_io(tl / 1.3)) if prev else 0
        push = 1 - 0.07 * ease_io(tl / max(sc["dur"], 1))
        cam = Camera(cv[0] + orbit + swing, cv[1] + 1.5 * math.sin(t * 0.37), cv[2] * push * (1 + 0.015 * math.sin(t * 0.5)),
                     cv[3], cv[4], cv[5])

        self.draw_grid(cam, t)
        self.draw_dust(cam, t)

        states = {}
        for oid, o in sc["objs"].items():
            st = self.obj_state(o, tl)
            if st:
                states[oid] = st
        outgoing = []
        for oid, o in sc["prev_objs"].items():
            if oid not in sc["objs"] or not sc["objs"][oid]["carried"]:
                st = self.outgoing_state(o, tl)
                if st:
                    outgoing.append(st)
        all_states = list(states.values()) + outgoing
        all_states.sort(key=lambda s: (s["o"]["type"] != "layer", -cam.proj((s["pos"][0], s["y"] + 0.5, s["pos"][1]))[2]))

        for st in all_states:
            self.draw_reflection(st, cam, t)
        for st in all_states:
            self.draw_floor_fx(st, cam, t)

        old_states = {s["o"]["id"]: s for s in outgoing}
        if tl < 0.45:
            for key, l in sc["prev_links"].items():
                if key not in sc["links"]:
                    self.draw_link(l, {**states, **old_states}, cam, tl, t, prog_override=1 - ease(tl / 0.45))
        for l in sc["links"].values():
            self.draw_link(l, states, cam, tl, t)

        for st in all_states:
            self.draw_object(st, cam, t)

        for b in sc["beats"]:
            if b["do"] == "flow" and tl >= b["t"]:
                l = sc["links"].get(f'{b["from"]}>{b["to"]}')
                lp = self.link_points(l, states) if l else None
                if lp:
                    p0, p1, a = lp
                    rgb = PALETTE.get(b.get("color", "cyan"), PALETTE["cyan"])
                    el = tl - b["t"]
                    for n in range(4):
                        u = (el - n * 0.3) / 1.2
                        if u < 0:
                            continue
                        self.packet(p0, p1, u % 1.0, cam, rgb, "", a * 0.9, arc=0.25)
            if b["do"] == "send" and b["t"] <= tl <= b["t"] + 1.6:
                A, B = states.get(b.get("from")), states.get(b.get("to"))
                if A and B:
                    rgb = PALETTE.get(b.get("color", "yellow"), ACCENT)
                    p0 = (A["pos"][0], A["y"] + obj_height(A["o"]["type"]) * A["o"]["size"] + 0.2, A["pos"][1])
                    p1 = (B["pos"][0], B["y"] + obj_height(B["o"]["type"]) * B["o"]["size"] + 0.2, B["pos"][1])
                    if tl <= b["t"] + 1.25:
                        u = ease_io((tl - b["t"]) / 0.95)
                        fade = 1 - ease((tl - b["t"] - 0.95) / 0.3)
                        self.packet(p0, p1, u, cam, rgb, b.get("label", ""), fade)
                    self.draw_sparks(cam, p1[0], p1[1], p1[2], (tl - b["t"] - 0.95) / 0.55, rgb)

        for st in all_states:
            self.draw_label(st, cam)

        texts = [b for b in sc["beats"] if b["do"] == "text"]
        for i, b in enumerate(texts):
            end = texts[i + 1]["t"] if i + 1 < len(texts) else sc["dur"] + 1
            if b["t"] <= tl < end + 0.3:
                out = ease((tl - end) / 0.3) if tl >= end else 0
                self.draw_callout(b.get("text", ""), (tl - b["t"]) / 0.45, (1 - out) * ease((tl - b["t"]) / 0.2),
                                  PALETTE.get(b.get("color", "yellow"), ACCENT))

        self.c.drawImage(self.vignette, 0, 0)
        hook_on = bool(self.hook) and t < HOOK_DUR
        if not hook_on or t > HOOK_DUR - 0.35:
            self.draw_header(sc, prev, tl, t)
        if t < total - 2.7 and not hook_on:
            self.draw_captions(sc, tl)
        self.draw_series_chip(ease((t - (HOOK_DUR if self.hook else 0)) / 0.5))
        if self.handle:
            self.text(self.handle, 1010, 165, MONO_BOLD, 20, (255, 255, 255), 0.5, "right")
        self.draw_hook(t)
        self.rrect(0, 1908, BASE_W * clamp(t / total), 12, 0, fill=ACCENT, a=0.85)
        self.draw_end_card(t, total)

        fade = min(clamp(t / 0.35), clamp((total - t) / 0.4))
        if fade < 1:
            self.c.drawRect(skia.Rect.MakeWH(self.w, self.h), self.fill_paint((5, 6, 10), 1 - fade))
        return self.buf

def prime_end_cams(r, scenes):
    for i, sc in enumerate(scenes):
        r.end_cams[i] = r.cam_at(i, sc["dur"], scenes)


def render_motion(scenes, durations, word_times, audio_path, out_path, width=2160, height=3840, fps=30, handle="", log=print,
                  theme=None, hook="", series_label=""):
    if theme:
        apply_theme(theme)
    compiled, total = compile_scenes(scenes, durations, word_times)
    r = MotionRenderer(width, height, fps, handle)
    r.hook, r.series_label = hook, series_label
    prime_end_cams(r, compiled)
    n_frames = int(math.ceil(total * fps))
    cmd = [ffmpeg_exe(), "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "bgra", "-s", f"{width}x{height}", "-r", str(fps), "-i", "-",
           "-i", str(audio_path),
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-rc-lookahead", "20",
           "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", "-shortest", str(out_path)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    t0 = time.time()
    try:
        for f in range(n_frames):
            proc.stdin.write(r.frame3d(compiled, f / fps, total).data)
            if f % (fps * 15) == 0:
                log(f"  frame {f}/{n_frames} ({time.time() - t0:.0f}s elapsed)")
    finally:
        proc.stdin.close()
        proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed with code {proc.returncode}")
    log(f"  rendered {n_frames} frames in {time.time() - t0:.0f}s")
    return total


def render_stills(scenes, durations, word_times, times, out_pattern, width=1080, height=1920, handle="",
                  theme=None, hook="", series_label=""):
    if theme:
        apply_theme(theme)
    compiled, total = compile_scenes(scenes, durations, word_times)
    r = MotionRenderer(width, height, 30, handle)
    r.hook, r.series_label = hook, series_label
    prime_end_cams(r, compiled)
    for i, t in enumerate(times):
        r.frame3d(compiled, t, total)
        r.surface.makeImageSnapshot().save(out_pattern % i, skia.kPNG)
