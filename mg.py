"""
Motion-graphics engine: premium 2D explainer videos built from motion primitives (shapes, rings, bars, counters,
icons) and motion connectors (self-drawing arrows with flowing dashes and travelling dots).

Each scene uses a layout chosen to fit what the narration explains (steps, flow, compare, stat, bars, cycle,
tree, stack, grid, timeline, hub, funnel, code, definition, pipeline), and every video is styled by its own
design DNA (style.py). Every element enters on the exact word that introduces it.
"""
import math
import subprocess
import time
from functools import lru_cache
from pathlib import Path

import numpy as np
import skia

import style as S

BASE = Path(__file__).parent
FONT_DIR = BASE / "assets" / "fonts"
DW, DH = 1080, 1920
STAGE = (60, 420, 960, 1180)          # x, y, w, h of the diagram area
LAYOUTS = ("steps", "flow", "compare", "stat", "bars", "cycle", "tree", "stack", "grid", "timeline", "hub",
           "funnel", "code", "definition", "pipeline")
LAYOUTS3D = ("holo_flow", "holo_hub", "holo_orbit", "holo_layers", "holo_cluster", "holo_pipeline", "holo_tree",
             "holo_chart", "holo_compare", "holo_timeline")
ICONS = ("server", "db", "cloud", "lock", "user", "phone", "laptop", "gear", "chart", "bolt", "check", "cross",
         "clock", "globe", "key", "file", "cpu", "search", "shield", "code", "star", "layers")


def ffmpeg_exe():
    import shutil
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def e_out(x):
    x = clamp(x)
    return 1 - (1 - x) ** 3


def e_io(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)


def e_back(x):
    x = clamp(x)
    c1 = 1.70158
    return 1 + (c1 + 1) * (x - 1) ** 3 + c1 * (x - 1) ** 2


def mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


ICON_DIR = BASE / "assets" / "icons"
SVG_ICONS = tuple(sorted(p.stem for p in ICON_DIR.glob("*.svg"))) if ICON_DIR.exists() else ()
ICONS = ICONS + tuple(n for n in SVG_ICONS if n not in ICONS)


@lru_cache(maxsize=None)
def _svg(name):
    path = ICON_DIR / f"{name}.svg"
    if not path.exists():
        return None
    try:
        return skia.SVGDOM.MakeFromStream(skia.Stream.MakeFromFile(str(path)))
    except Exception:
        return None


@lru_cache(maxsize=None)
def tf(name):
    return skia.Typeface.MakeFromFile(str(FONT_DIR / f"{name}.ttf"))


def bezier(p0, p1, p2, p3, n=28):
    out = []
    for i in range(n + 1):
        u = i / n
        a, b, c, d = (1 - u) ** 3, 3 * u * (1 - u) ** 2, 3 * u * u * (1 - u), u ** 3
        out.append((a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0], a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1]))
    return out


def densify(pts, n=12):
    out = []
    for i in range(len(pts) - 1):
        for j in range(n):
            u = j / n
            out.append((pts[i][0] + (pts[i + 1][0] - pts[i][0]) * u, pts[i][1] + (pts[i + 1][1] - pts[i][1]) * u))
    out.append(pts[-1])
    return out


def trim(pts, frac):
    """First `frac` of a polyline by length."""
    if frac >= 1:
        return pts
    segs = [math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]) for i in range(len(pts) - 1)]
    target, acc, out = sum(segs) * clamp(frac), 0.0, [pts[0]]
    for i, s in enumerate(segs):
        if acc + s >= target:
            u = (target - acc) / (s or 1)
            out.append((pts[i][0] + (pts[i + 1][0] - pts[i][0]) * u, pts[i][1] + (pts[i + 1][1] - pts[i][1]) * u))
            return out
        acc += s
        out.append(pts[i + 1])
    return out


class G:
    """Drawing helpers in design units (1080x1920) on a canvas scaled to the output resolution."""

    def __init__(self, canvas, k, dna):
        self.c, self.k = canvas, k
        self.pal = S.palette(dna["palette"], dna["rot"])
        self.fonts = S.FONT_PAIRS[dna["fonts"]]
        self.dna = dna
        self.cache = {}

    def col(self, rgb, a=1.0):
        return skia.Color(int(rgb[0]), int(rgb[1]), int(rgb[2]), int(255 * clamp(a)))

    def fill(self, rgb, a=1.0):
        return skia.Paint(AntiAlias=True, Color=self.col(rgb, a))

    def stroke(self, rgb, a=1.0, w=2.0, dash=None, phase=0.0):
        p = skia.Paint(AntiAlias=True, Color=self.col(rgb, a), Style=skia.Paint.kStroke_Style, StrokeWidth=w * self.k,
                       StrokeCap=skia.Paint.kRound_Cap, StrokeJoin=skia.Paint.kRound_Join)
        if dash:
            p.setPathEffect(skia.DashPathEffect.Make([d * self.k for d in dash], phase * self.k))
        return p

    # ---- text (rasterised once per string/size/colour)
    def width(self, s, font, size):
        return skia.Font(tf(font), size).measureText(s)

    def ext_vec(self):
        return {"left": (0.55, 1.0), "right": (-0.55, 1.0), "top": (0.0, 1.0)}[self.dna.get("light", "left")]

    def ext_depth(self):
        return {"shallow": 8, "deep": 14, "long": 22}[self.dna.get("depth", "deep")]

    def text(self, s, x, y, size, rgb, font=None, align="left", a=1.0, depth=0, ex=None):
        """Text rasterised once per string/size/colour; depth > 0 bakes in a 3D extrusion (away from the light)."""
        if not s or a <= 0.003:
            return 0
        font = font or self.fonts[1]
        size = round(size)
        key = (s, font, size, rgb, depth, ex)
        hit = self.cache.get(key)
        if hit is None:
            f = skia.Font(tf(font), size * self.k)
            f.setSubpixel(True)
            m = f.getMetrics()
            ux, uy = self.ext_vec()
            dpx = depth * self.k
            padl, padr = int(math.ceil(max(0.0, -ux) * dpx)), int(math.ceil(max(0.0, ux) * dpx))
            fw = f.measureText(s)
            w = max(1, int(math.ceil(fw)) + 4 + padl + padr)
            h = max(1, int(math.ceil(m.fDescent - m.fAscent + uy * dpx)) + 4)
            surf = skia.Surface(w, h)
            cv = surf.getCanvas()
            cv.clear(skia.ColorTRANSPARENT)
            bx, by = 2 + padl, 2 - m.fAscent
            if depth:
                n = max(1, int(dpx))
                exc = ex or mix(rgb, (0, 0, 0), 0.5)
                for i in range(n, 0, -1):
                    cv.drawString(s, bx + ux * dpx * i / n, by + uy * dpx * i / n, f,
                                  skia.Paint(AntiAlias=True, Color=self.col(mix(exc, (0, 0, 0), 0.35 * i / n))))
            cv.drawString(s, bx, by, f, skia.Paint(AntiAlias=True, Color=self.col(rgb)))
            hit = (surf.makeImageSnapshot(), -m.fAscent + 2, padl, fw / self.k)
            if len(self.cache) > 5000:
                self.cache.clear()
            self.cache[key] = hit
        img, asc, padl, wd = hit
        if align == "center":
            x -= wd / 2
        elif align == "right":
            x -= wd
        self.c.drawImage(img, x * self.k - padl - 2, y * self.k - asc, skia.SamplingOptions(skia.FilterMode.kLinear),
                         skia.Paint(Alphaf=clamp(a)))
        return wd

    def fit(self, s, font, size, max_w, lo=0.5):
        z = size
        while z > size * lo and self.width(s, font, z) > max_w:
            z -= 2
        return z

    def wrap(self, s, font, size, max_w, max_lines=3):
        lines, cur = [], ""
        for w in s.split():
            t = (cur + " " + w).strip()
            if cur and self.width(t, font, size) > max_w:
                lines.append(cur)
                cur = w
            else:
                cur = t
        if cur:
            lines.append(cur)
        return lines[:max_lines]

    # ---- shapes
    def shape_path(self, x, y, w, h, kind=None):
        k = self.k
        kind = kind or self.dna["shape"]
        r = {"rounded": 22, "sharp": 4, "pill": min(w, h) / 2, "soft": 38, "cut": 0}.get(kind, 20)
        r = min(r, w / 2, h / 2)
        p = skia.Path()
        if kind == "cut":
            c = min(26, w / 4, h / 4)
            pts = [(x + c, y), (x + w, y), (x + w, y + h - c), (x + w - c, y + h), (x, y + h), (x, y + c)]
            p.moveTo(pts[0][0] * k, pts[0][1] * k)
            for q in pts[1:]:
                p.lineTo(q[0] * k, q[1] * k)
            p.close()
        else:
            p.addRRect(skia.RRect.MakeRectXY(skia.Rect.MakeXYWH(x * k, y * k, w * k, h * k), r * k, r * k))
        return p

    def shadow_col(self):
        return mix(self.pal["bg"], (0, 0, 0), 0.12 if self.pal["light"] else 0.5)

    def side_col(self, accent=None):
        if accent and self.dna["shadow"] == "none":
            return mix(accent, (0, 0, 0), 0.35)
        return mix(self.pal["bg"], (0, 0, 0), 0.22 if self.pal["light"] else 0.5)

    def card(self, x, y, w, h, rgb, a=1.0, accent=None, depth=None):
        """A 3D extruded card: stacked side layers away from the light, then the face."""
        d = self.ext_depth() if depth is None else depth
        ux, uy = self.ext_vec()
        side = self.side_col(accent)
        path = self.shape_path(x, y, w, h)
        steps = max(2, int(d / 4))
        for i in range(steps, 0, -1):
            off = d * i / steps
            self.c.save()
            self.c.translate(ux * off * self.k, uy * off * self.k)
            self.c.drawPath(path, self.fill(side, a))
            self.c.restore()
        self.c.drawPath(path, self.fill(rgb, a))
        if self.dna["shadow"] == "outline" and accent:
            self.c.drawPath(path, self.stroke(accent, a, 3))

    def chip(self, s, x, y, size, acc, a=1.0, align="center", txt=None):
        """A 3D label: extruded plate with extruded text."""
        font = self.fonts[0]
        w, h = self.width(s, font, size) + 40, size + 26
        x0 = x - w / 2 if align == "center" else (x if align == "left" else x - w)
        x0 = max(24, min(DW - 24 - w - 22, x0))      # keep 3D labels on screen
        self.card(x0, y - h / 2, w, h, self.pal["surface"], a, acc, depth=9)
        self.c.drawPath(self.shape_path(x0, y - h / 2, 8, h, "sharp"), self.fill(acc, a))
        self.text(s, x0 + 22, y + size * 0.36, size, txt or self.pal["text"], font, a=a, depth=2, ex=acc)

    def circle(self, x, y, r, rgb, a=1.0):
        if r > 0:
            self.c.drawCircle(x * self.k, y * self.k, r * self.k, self.fill(rgb, a))

    def ring(self, x, y, r, rgb, a=1.0, w=3.0, sweep=360, start=-90):
        k = self.k
        if r <= 0:
            return
        if sweep >= 359.9:
            self.c.drawCircle(x * k, y * k, r * k, self.stroke(rgb, a, w))
        elif sweep > 0.1:
            self.c.drawArc(skia.Rect.MakeXYWH((x - r) * k, (y - r) * k, 2 * r * k, 2 * r * k), start, sweep, False,
                           self.stroke(rgb, a, w))

    def poly(self, pts, rgb, a=1.0, w=3.0, dash=None, phase=0.0, close=False, filled=False):
        if len(pts) < 2:
            return
        k = self.k
        p = skia.Path()
        p.moveTo(pts[0][0] * k, pts[0][1] * k)
        for q in pts[1:]:
            p.lineTo(q[0] * k, q[1] * k)
        if close:
            p.close()
        self.c.drawPath(p, self.fill(rgb, a) if filled else self.stroke(rgb, a, w, dash, phase))

    # ---- icons (user SVG assets from assets/icons, else built-in vector glyphs) centred at x,y with size s
    def icon(self, name, x, y, s, rgb, a=1.0):
        dom = _svg(name)
        if dom is not None:
            k = self.k
            self.c.save()
            self.c.translate((x - s / 2) * k, (y - s / 2) * k)
            dom.setContainerSize(skia.Size(s * k, s * k))
            self.c.saveLayer(skia.Rect.MakeWH(s * k, s * k), skia.Paint(
                Alphaf=clamp(a), ColorFilter=skia.ColorFilters.Blend(self.col(rgb), skia.BlendMode.kSrcIn)))
            dom.render(self.c)
            self.c.restore()
            self.c.restore()
            return
        w = max(2.0, s * 0.07)
        k = self.k

        def P(pts, close=False):
            self.poly([(x + px * s, y + py * s) for px, py in pts], rgb, a, w, close=close)

        def arc(cx, cy, rw, rh, st, sw):
            self.c.drawArc(skia.Rect.MakeXYWH((x + (cx - rw) * s) * k, (y + (cy - rh) * s) * k, 2 * rw * s * k,
                                              2 * rh * s * k), st, sw, False, self.stroke(rgb, a, w))

        if name == "server":
            for i in range(3):
                P([(-.35, -.4 + i * .28), (.35, -.4 + i * .28), (.35, -.18 + i * .28), (-.35, -.18 + i * .28)], True)
        elif name == "db":
            for yy in (-.3, 0, .3):
                arc(0, yy, .32, .08, 0, 360 if yy == -.3 else 180)
            P([(-.32, -.3), (-.32, .3)])
            P([(.32, -.3), (.32, .3)])
        elif name == "cloud":
            arc(-.17, .05, .17, .17, 90, 180)
            arc(.05, -.06, .22, .22, 180, 180)
            arc(.22, .07, .15, .15, 270, 180)
            P([(-.17, .22), (.22, .22)])
        elif name == "lock":
            P([(-.3, -.02), (.3, -.02), (.3, .38), (-.3, .38)], True)
            arc(0, -.1, .18, .2, 180, 180)
        elif name == "user":
            self.ring(x, y - .15 * s, .14 * s, rgb, a, w)
            arc(0, .3, .3, .25, 180, 180)
        elif name == "phone":
            P([(-.2, -.38), (.2, -.38), (.2, .38), (-.2, .38)], True)
            P([(-.06, .28), (.06, .28)])
        elif name == "laptop":
            P([(-.3, -.25), (.3, -.25), (.3, .12), (-.3, .12)], True)
            P([(-.42, .22), (.42, .22)])
        elif name == "gear":
            self.ring(x, y, .2 * s, rgb, a, w)
            for i in range(8):
                ang = i * math.pi / 4
                P([(math.cos(ang) * .25, math.sin(ang) * .25), (math.cos(ang) * .38, math.sin(ang) * .38)])
        elif name == "chart":
            P([(-.35, .35), (.38, .35)])
            for i, hgt in enumerate((.25, .45, .62)):
                P([(-.2 + i * .22, .35), (-.2 + i * .22, .35 - hgt)])
        elif name == "bolt":
            P([(.08, -.4), (-.18, .05), (.02, .05), (-.08, .4), (.2, -.08), (0, -.08)], True)
        elif name == "check":
            P([(-.3, 0), (-.08, .22), (.32, -.22)])
        elif name == "cross":
            P([(-.25, -.25), (.25, .25)])
            P([(.25, -.25), (-.25, .25)])
        elif name == "clock":
            self.ring(x, y, .34 * s, rgb, a, w)
            P([(0, 0), (0, -.2)])
            P([(0, 0), (.15, .08)])
        elif name == "globe":
            self.ring(x, y, .34 * s, rgb, a, w)
            P([(-.34, 0), (.34, 0)])
            arc(0, 0, .14, .34, 0, 360)
        elif name == "key":
            self.ring(x - .18 * s, y, .14 * s, rgb, a, w)
            P([(-.04, 0), (.36, 0), (.36, .12)])
            P([(.22, 0), (.22, .1)])
        elif name == "file":
            P([(-.24, -.36), (.1, -.36), (.24, -.22), (.24, .36), (-.24, .36)], True)
            for i in range(3):
                P([(-.12, -.08 + i * .13), (.12, -.08 + i * .13)])
        elif name == "cpu":
            P([(-.24, -.24), (.24, -.24), (.24, .24), (-.24, .24)], True)
            for i in (-1, 0, 1):
                P([(i * .12, -.24), (i * .12, -.36)])
                P([(i * .12, .24), (i * .12, .36)])
                P([(-.24, i * .12), (-.36, i * .12)])
                P([(.24, i * .12), (.36, i * .12)])
        elif name == "search":
            self.ring(x - .06 * s, y - .06 * s, .22 * s, rgb, a, w)
            P([(.1, .1), (.32, .32)])
        elif name == "shield":
            P([(0, -.38), (.3, -.25), (.26, .12), (0, .38), (-.26, .12), (-.3, -.25)], True)
        elif name == "code":
            P([(-.12, -.22), (-.32, 0), (-.12, .22)])
            P([(.12, -.22), (.32, 0), (.12, .22)])
        elif name == "star":
            pts = []
            for i in range(10):
                r = .36 if i % 2 == 0 else .15
                ang = -math.pi / 2 + i * math.pi / 5
                pts.append((math.cos(ang) * r, math.sin(ang) * r))
            P(pts, True)
        else:  # layers
            for i in range(3):
                P([(-.32, -.1 + i * .16), (0, -.24 + i * .16), (.32, -.1 + i * .16), (0, .04 + i * .16)], True)


# ===================================================================== motion
def entrance(dna, p):
    """(scale, dx, dy, alpha, scale_x) for an element p (0..1) into its entrance."""
    style, m = dna["entrance"], dna["motion"]
    ez = e_back if m == "bouncy" else (e_out if m == "snappy" else e_io)
    u = ez(p)
    a = clamp(p * 2.2)
    if style == "pop":
        return 0.6 + 0.4 * u, 0, 0, a, 1
    if style == "slide":
        return 1, -80 * (1 - u), 0, a, 1
    if style == "drop":
        return 1, 0, -90 * (1 - u), a, 1
    if style == "flip":
        return 1, 0, 0, a, max(0.02, u)
    return 1, 0, 0, a, 1     # grow: width reveal handled by the caller


def enter_dur(dna):
    return {"snappy": 0.38, "smooth": 0.6, "bouncy": 0.55}[dna["motion"]]


# ===================================================================== layouts -> node geometry + links
def layout_scene(sc):
    L = sc["layout"]
    items = sc["items"]
    if L in LAYOUTS3D:
        return {"nodes": [{"item": it} for it in items], "links": []}
    n = len(items)
    x0, y0, W, H = STAGE
    nodes, links = [], []
    if L == "steps":
        rh = min(250, H / max(n, 1))
        for i in range(n):
            nodes.append(dict(x=x0 + 120, y=y0 + i * rh + 10, w=W - 120, h=rh - 34, badge=i + 1))
        links = [(i, i + 1) for i in range(n - 1)]
    elif L == "flow":
        rh = min(330, H / max(n, 1))
        for i in range(n):
            left = i % 2 == 0
            nodes.append(dict(x=x0 + (0 if left else W - 560), y=y0 + i * rh + 10, w=560, h=rh - 80))
        links = [(i, i + 1) for i in range(n - 1)]
    elif L == "compare":
        rh = min(220, (H - 170) / max(n, 1))
        for i in range(n):
            nodes.append(dict(x=x0, y=y0 + 170 + i * rh, w=W, h=rh - 26))
    elif L == "stat":
        nodes.append(dict(x=x0 + 90, y=y0 + 20, w=W - 180, h=560, big=True))
        m = n - 1
        for i in range(1, n):
            cw = (W - 30 * (m - 1)) / max(1, m)
            nodes.append(dict(x=x0 + (i - 1) * (cw + 30), y=y0 + 660, w=cw, h=220, mini=True))
    elif L == "bars":
        rh = min(220, H / max(n, 1))
        for i in range(n):
            nodes.append(dict(x=x0, y=y0 + i * rh + 20, w=W, h=rh - 40))
    elif L == "cycle":
        cx, cy, R = x0 + W / 2, y0 + H / 2, min(W, H) / 2 - 150
        for i in range(n):
            ang = -math.pi / 2 + 2 * math.pi * i / n
            nodes.append(dict(x=cx + R * math.cos(ang) - 100, y=cy + R * math.sin(ang) - 100, w=200, h=200, round=True))
        links = [(i, (i + 1) % n) for i in range(n)]
    elif L == "tree":
        root_w = 440
        nodes.append(dict(x=x0 + W / 2 - root_w / 2, y=y0 + 20, w=root_w, h=170))
        kids = list(range(1, n))
        row1 = [i for i in kids if int(items[i].get("parent", 0) or 0) == 0][:4] or kids[:4]
        row2 = [i for i in kids if i not in row1]
        geo = {}
        cw = min(300, (W - 30 * (len(row1) - 1)) / max(1, len(row1)))
        tot = len(row1) * cw + (len(row1) - 1) * 30
        for j, i in enumerate(row1):
            geo[i] = dict(x=x0 + W / 2 - tot / 2 + j * (cw + 30), y=y0 + 410, w=cw, h=210, mini=True)
            links.append((0, i))
        if row2:
            cw2 = min(300, (W - 30 * (len(row2) - 1)) / len(row2))
            tot2 = len(row2) * cw2 + (len(row2) - 1) * 30
            for j, i in enumerate(row2):
                geo[i] = dict(x=x0 + W / 2 - tot2 / 2 + j * (cw2 + 30), y=y0 + 800, w=cw2, h=210, mini=True)
                par = int(items[i].get("parent", 0) or 0)
                links.append((par if par in row1 else row1[min(j, len(row1) - 1)], i))
        nodes += [geo[i] for i in range(1, n)]
    elif L == "stack":
        lh = min(230, H / max(n, 1))
        for i in range(n):
            inset = i * 22
            nodes.append(dict(x=x0 + inset, y=y0 + H - (i + 1) * lh, w=W - 2 * inset, h=lh - 22))
    elif L == "grid":
        cols = 2
        rows = math.ceil(n / cols)
        cw, chh = (W - 30) / cols, min(420, (H - 30 * (rows - 1)) / rows)
        for i in range(n):
            nodes.append(dict(x=x0 + (i % cols) * (cw + 30), y=y0 + (i // cols) * (chh + 30), w=cw, h=chh, tile=True))
    elif L == "timeline":
        rh = H / max(n, 1)
        for i in range(n):
            left = i % 2 == 0
            nodes.append(dict(x=x0 + (0 if left else W / 2 + 50), y=y0 + i * rh + 20, w=W / 2 - 50, h=rh - 50,
                              side="L" if left else "R"))
    elif L == "hub":
        cx, cy = x0 + W / 2, y0 + H / 2
        nodes.append(dict(x=cx - 140, y=cy - 140, w=280, h=280, round=True, hub=True))
        m = n - 1
        R = min(W, H) / 2 - 120
        for i in range(m):
            ang = -math.pi / 2 + 2 * math.pi * i / max(m, 1)
            nodes.append(dict(x=cx + R * math.cos(ang) - 90, y=cy + R * math.sin(ang) - 90, w=180, h=180, round=True))
            links.append((0, i + 1))
    elif L == "funnel":
        rh = min(240, H / max(n, 1))
        for i in range(n):
            inset = i * (W * 0.3 / max(n - 1, 1))
            nodes.append(dict(x=x0 + inset, y=y0 + i * rh + 10, w=W - 2 * inset, h=rh - 26, funnel=True))
    elif L == "code":
        lines = items[0].get("lines") or []
        nodes.append(dict(x=x0, y=y0 + 60, w=W, h=min(H - 100, 180 + len(lines) * 76), terminal=True))
        for i in range(1, n):
            nodes.append(dict(x=x0, y=nodes[0]["y"] + nodes[0]["h"] + 40 + (i - 1) * 130, w=W, h=100))
    elif L == "definition":
        nodes.append(dict(x=x0, y=y0 + 30, w=W, h=580, definition=True))
        m = n - 1
        for i in range(1, n):
            cw = (W - 30 * (m - 1)) / max(1, m)
            nodes.append(dict(x=x0 + (i - 1) * (cw + 30), y=y0 + 690, w=cw, h=210, mini=True))
    elif L == "pipeline":
        cols = min(n, 3)
        cw = (W - 60 * (cols - 1)) / cols
        for i in range(n):
            r, cpos = divmod(i, cols)
            if r % 2 == 1:
                cpos = cols - 1 - cpos
            nodes.append(dict(x=x0 + cpos * (cw + 60), y=y0 + 60 + r * 360, w=cw, h=250, tile=True))
        links = [(i, i + 1) for i in range(n - 1)]
    if nodes and L not in ("cycle", "hub"):        # centre the composition in the stage
        top = min(nd["y"] for nd in nodes)
        bot = max(nd["y"] + nd["h"] for nd in nodes)
        shift = (y0 + H / 2) - (top + bot) / 2
        for nd in nodes:
            nd["y"] += shift
    for nd, it in zip(nodes, items):
        nd["item"] = it
    return {"nodes": nodes[:n], "links": [(a, b) for a, b in links if a < len(nodes) and b < len(nodes)]}


# ===================================================================== renderer
class Video:
    def __init__(self, script, durations, word_times, dna, width=2160, height=3840, fps=30, handle=""):
        self.sc, self.dna, self.fps, self.handle = script, dna, fps, handle
        self.w, self.h, self.k = width, height, width / DW
        info = skia.ImageInfo.Make(width, height, skia.kBGRA_8888_ColorType, skia.kPremul_AlphaType)
        self.buf = np.zeros((height, width, 4), np.uint8)
        self.surface = skia.Surface.MakeRasterDirect(info, self.buf)
        self.g = G(self.surface.getCanvas(), self.k, dna)
        self.pal = self.g.pal
        self.bg = self._background()
        self.scenes, t = [], 0.0
        for scn, dur, words in zip(script["scenes"], durations, word_times):
            geo = layout_scene(scn) if scn["layout"] != "hook" else {"nodes": [], "links": []}
            ptr = 0
            for j, nd in enumerate(geo["nodes"]):
                idx = self._match(nd["item"].get("cue", ""), words, ptr)
                nd["t"] = (words[idx][1] - 0.08) if idx is not None else 0.6 + j * max(0.5, (dur - 3) / max(1, len(geo["nodes"])))
                if idx is not None:
                    ptr = idx + 1
                nd["acc"] = self.pal["accents"][j % len(self.pal["accents"])]
                nd["emph"] = None
                nd["sib"] = geo["nodes"]
                if nd.get("terminal"):
                    nd["line_t"] = []
                    for ln, cue in zip(nd["item"].get("lines", []), nd["item"].get("line_cues", [])):
                        ix = self._match(cue, words, 0)
                        nd["line_t"].append(words[ix][1] if ix is not None else None)
            for em in scn.get("emphasis", []) or []:
                idx = self._match(em.get("cue", ""), words, 0)
                it = em.get("item", -1)
                if idx is not None and isinstance(it, int) and 0 <= it < len(geo["nodes"]):
                    geo["nodes"][it]["emph"] = words[idx][1]
            self.scenes.append({"start": t, "dur": dur, "data": scn, "geo": geo, "chunks": self._chunks(words)})
            t += dur
        self.total = t
        rng = np.random.default_rng(dna["seed"] % 100000)
        self.floaters = [(rng.uniform(0, DW), rng.uniform(0, DH), rng.uniform(26, 80), rng.uniform(0.3, 0.9),
                          int(rng.integers(0, 4))) for _ in range(10)]

    def sound_events(self):
        """(time, kind) list for the sound designer."""
        ev = []
        for i, s in enumerate(self.scenes):
            if i:
                ev.append((s["start"] - 0.2, "whoosh"))
            for nd in s["geo"]["nodes"]:
                ev.append((s["start"] + nd["t"], "pop"))
            for a, b in s["geo"]["links"]:
                nA, nB = s["geo"]["nodes"][a], s["geo"]["nodes"][b]
                ev.append((s["start"] + max(nA["t"], nB["t"]) + 0.1, "tick"))
        return ev

    @staticmethod
    def _norm(w):
        return "".join(ch for ch in w.lower() if ch.isalnum())

    def _match(self, cue, words, start):
        toks = [self._norm(w) for w in str(cue).split() if self._norm(w)]
        ws = [self._norm(w[0]) for w in words]
        if not toks:
            return None
        for b in (start, 0):
            for i in range(b, len(ws) - len(toks) + 1):
                if ws[i:i + len(toks)] == toks:
                    return i
        for i in range(start, len(ws)):        # fall back to the first cue word
            if ws[i] == toks[0]:
                return i
        return None

    @staticmethod
    def _chunks(words):
        out, cur = [], []
        for w in words:
            if cur and (len(cur) >= 3 or w[1] - cur[-1][2] > 0.25):
                out.append(cur)
                cur = []
            cur.append(w)
        if cur:
            out.append(cur)
        return out

    # ---------------------------------------------------------------- background (rendered once per video)
    def _background(self):
        surf = skia.Surface(self.w, self.h)
        c, k, pal, g = surf.getCanvas(), self.k, self.pal, self.g
        top, bot = pal["bg"], mix(pal["bg"], pal["accents"][0], 0.10)
        c.drawPaint(skia.Paint(Shader=skia.GradientShader.MakeLinear([skia.Point(0, 0), skia.Point(0, self.h)],
                                                                    [g.col(top), g.col(bot)])))
        c.drawPaint(skia.Paint(Shader=skia.GradientShader.MakeRadial(skia.Point(self.w * 0.85, self.h * 0.12), self.w * 0.9,
                                                                    [g.col(pal["accents"][1], 0.16), g.col(pal["accents"][1], 0)])))
        c.drawPaint(skia.Paint(Shader=skia.GradientShader.MakeRadial(skia.Point(self.w * 0.1, self.h * 0.9), self.w * 0.8,
                                                                    [g.col(pal["accents"][2], 0.10), g.col(pal["accents"][2], 0)])))
        ink = mix(pal["bg"], pal["text"], 0.08)
        pat = self.dna["bg_pattern"]
        p = skia.Paint(AntiAlias=True, Color=g.col(ink), Style=skia.Paint.kStroke_Style, StrokeWidth=2 * k)
        f = skia.Paint(AntiAlias=True, Color=g.col(ink))
        if pat == "dots":
            for yy in range(0, DH, 44):
                for xx in range(0, DW, 44):
                    c.drawCircle(xx * k, yy * k, 2.4 * k, f)
        elif pat == "grid":
            for xx in range(0, DW, 72):
                c.drawLine(xx * k, 0, xx * k, self.h, p)
            for yy in range(0, DH, 72):
                c.drawLine(0, yy * k, self.w, yy * k, p)
        elif pat == "diagonal":
            for d in range(-DH, DW, 56):
                c.drawLine(d * k, 0, (d + DH) * k, self.h, p)
        elif pat == "rings":
            for r in range(80, 1700, 90):
                c.drawCircle(DW * 0.9 * k, DH * 0.1 * k, r * k, p)
        elif pat == "waves":
            for yy in range(0, DH + 80, 70):
                path = skia.Path()
                path.moveTo(0, yy * k)
                for xx in range(0, DW + 20, 20):
                    path.lineTo(xx * k, (yy + 14 * math.sin(xx / 70 + yy / 140)) * k)
                c.drawPath(path, p)
        elif pat == "crosses":
            for yy in range(30, DH, 90):
                for xx in range(30, DW, 90):
                    c.drawLine((xx - 7) * k, yy * k, (xx + 7) * k, yy * k, p)
                    c.drawLine(xx * k, (yy - 7) * k, xx * k, (yy + 7) * k, p)
        elif pat == "halftone":
            for yy in range(0, DH, 36):
                for xx in range(0, DW, 36):
                    c.drawCircle(xx * k, yy * k, (0.5 + 4.5 * (1 - yy / DH) * (xx / DW)) * k, f)
        return surf.makeImageSnapshot().makeRasterImage()

    # ---------------------------------------------------------------- frame
    def frame(self, t):
        g, pal = self.g, self.pal
        g.c.drawImage(self.bg, 0, 0)
        for (fx, fy, r, sp, kind) in self.floaters:          # drifting background primitives
            yy = (fy - t * 22 * sp) % (DH + 200) - 100
            xx = fx + 34 * math.sin(t * 0.5 * sp + fy)
            colr = mix(pal["bg"], pal["accents"][kind], 0.3)
            rot = t * sp
            if kind == 0:
                g.ring(xx, yy, r, colr, 1, 3)
            elif kind == 1:
                g.poly([(xx + r / 2 * math.cos(rot), yy + r / 2 * math.sin(rot)), (xx - r / 2 * math.cos(rot), yy - r / 2 * math.sin(rot))], colr, 1, 3)
                g.poly([(xx - r / 2 * math.sin(rot), yy + r / 2 * math.cos(rot)), (xx + r / 2 * math.sin(rot), yy - r / 2 * math.cos(rot))], colr, 1, 3)
            elif kind == 2:
                g.poly([(xx + r / 2 * math.cos(rot + j * 2.094), yy + r / 2 * math.sin(rot + j * 2.094)) for j in range(3)], colr, 1, 3, close=True)
            else:
                g.poly([(xx + r / 2 * math.cos(rot + j * 1.571), yy + r / 2 * math.sin(rot + j * 1.571)) for j in range(4)], colr, 1, 3, close=True)
        si = 0
        for i, s in enumerate(self.scenes):
            if t >= s["start"]:
                si = i
        s = self.scenes[si]
        tl = t - s["start"]
        if s["data"]["layout"] == "hook":
            self.draw_hook(s, tl)
        else:
            self.draw_header(s, si, tl)
            self.draw_scene(s, tl, t)
        self.draw_captions(s, tl)
        self.draw_chrome(t)
        self.draw_transition(t)
        self.draw_end(t)
        return self.buf

    def draw_chrome(self, t):
        g, pal = self.g, self.pal
        g.c.drawRect(skia.Rect.MakeXYWH(0, (DH - 10) * self.k, DW * clamp(t / self.total) * self.k, 10 * self.k), g.fill(pal["accents"][0]))
        if self.handle:
            g.text(self.handle, DW - 50, 90, 24, pal["muted"], g.fonts[1], "right")

    def draw_header(self, s, si, tl):
        g, pal, dna = self.g, self.pal, self.dna
        title = s["data"].get("title", "")
        u = e_out(tl / 0.55)
        n = len(self.scenes) - 1
        tfont = g.fonts[0]
        acc = pal["accents"][si % 4]
        k = self.k
        style = dna["header"]
        if style == "kicker":
            g.text(f"{si:02d} / {n:02d}", 60, 170, 28, acc, g.fonts[2], a=u)
            g.c.drawRect(skia.Rect.MakeXYWH(200 * k, 160 * k, 120 * u * k, 4 * k), g.fill(acc))
            size = g.fit(title, tfont, 68, 960, 0.7)
            for li, ln in enumerate(g.wrap(title, tfont, size, 960, 2)):
                g.text(ln, 60 + 40 * (1 - u), 255 + li * size * 1.1, size, pal["text"], tfont, a=u, depth=5, ex=acc)
        elif style == "centered":
            size = g.fit(title, tfont, 66, 940, 0.7)
            lines = g.wrap(title, tfont, size, 940, 2)
            for li, ln in enumerate(lines):
                g.text(ln, DW / 2, 225 + li * size * 1.1 + 30 * (1 - u), size, pal["text"], tfont, "center", u, depth=5, ex=acc)
            bw = 140 * u
            g.c.drawRect(skia.Rect.MakeXYWH((DW / 2 - bw / 2) * k, (255 + (len(lines) - 1) * size * 1.1) * k, bw * k, 8 * k), g.fill(acc))
        elif style == "bignum":
            g.text(f"{si:02d}", 50, 335, 230, mix(pal["bg"], acc, 0.4), tfont, a=u, depth=12, ex=mix(acc, (0, 0, 0), 0.3))
            size = g.fit(title, tfont, 58, 690, 0.7)
            for li, ln in enumerate(g.wrap(title, tfont, size, 690, 2)):
                g.text(ln, 340 + 30 * (1 - u), 235 + li * size * 1.12, size, pal["text"], tfont, a=u, depth=5, ex=acc)
        else:  # chip
            label = f"PART {si}"
            cw = g.width(label, g.fonts[2], 24) + 44
            g.c.drawPath(g.shape_path(60, 140, cw * u + 1, 50, "pill"), g.fill(acc))
            g.text(label, 82, 175, 24, pal["bg"], g.fonts[2], a=u)
            size = g.fit(title, tfont, 64, 960, 0.7)
            for li, ln in enumerate(g.wrap(title, tfont, size, 960, 2)):
                g.text(ln, 60, 285 + li * size * 1.1 + 24 * (1 - u), size, pal["text"], tfont, a=u, depth=5, ex=acc)

    def draw_scene(self, s, tl, t):
        g, pal = self.g, self.pal
        L = s["data"]["layout"]
        if L in LAYOUTS3D:
            d3.draw(self, s, tl, t)
            return
        nodes, links = s["geo"]["nodes"], s["geo"]["links"]
        if L == "compare":
            self.draw_compare_head(s, tl)
        if L == "timeline":
            top, bot = nodes[0]["y"] - 20, nodes[-1]["y"] + nodes[-1]["h"] + 20
            g.poly([(DW / 2, top), (DW / 2, top + (bot - top) * e_io(tl / 1.2))], mix(pal["bg"], pal["text"], 0.3), 1, 5)
        if L == "funnel" and nodes:
            last = nodes[-1]
            if tl > last["t"] + 0.4:
                u = e_out((tl - last["t"] - 0.4) / 0.6)
                ax = DW / 2
                g.poly([(ax, last["y"] + last["h"] + 8), (ax, last["y"] + last["h"] + 8 + 30 * u)], pal["accents"][0], 1, 6)
        for a, b in links:
            self.draw_connector(nodes[a], nodes[b], tl, t, L)
        if L == "cycle" and nodes and tl > max(nd["t"] for nd in nodes) + 0.6:
            cx, cy = STAGE[0] + STAGE[2] / 2, STAGE[1] + STAGE[3] / 2
            R = min(STAGE[2], STAGE[3]) / 2 - 150
            ang = -math.pi / 2 + t * 1.3
            g.circle(cx + R * math.cos(ang), cy + R * math.sin(ang), 13, pal["accents"][1])
            g.ring(cx, cy, 70, mix(pal["bg"], pal["accents"][0], 0.5), 1, 4, sweep=300, start=math.degrees(t * 2))
        for i, nd in enumerate(nodes):
            p = clamp((tl - nd["t"]) / enter_dur(self.dna))
            if p > 0:
                self.draw_node(nd, p, tl, t, L, i)

    def draw_compare_head(self, s, tl):
        g, pal = self.g, self.pal
        d = s["data"]
        u = e_out(tl / 0.5)
        x0, y0, W, _ = STAGE
        for j, (lab, ax) in enumerate(((d.get("left_title") or "Before", x0), (d.get("right_title") or "After", x0 + W / 2 + 15))):
            acc = pal["accents"][j]
            g.card(ax, y0 + 10 - 40 * (1 - u), W / 2 - 15, 120, acc, u)
            size = g.fit(lab, g.fonts[0], 46, W / 2 - 120)
            g.text(lab, ax + (W / 2 - 15) / 2, y0 + 90 - 40 * (1 - u), size, pal["bg"], g.fonts[0], "center", u)
        cx = x0 + W / 2
        r = 50 * e_back(tl / 0.6)
        g.circle(cx, y0 + 70, r, pal["text"])
        g.text("VS", cx, y0 + 84, 34, pal["bg"], g.fonts[0], "center", clamp(r / 50))

    def anchors(self, A, B, L):
        ax, ay = A["x"] + A["w"] / 2, A["y"] + A["h"] / 2
        bx, by = B["x"] + B["w"] / 2, B["y"] + B["h"] / 2
        if L == "steps":
            return (A["x"] - 60, A["y"] + A["h"] / 2 + 44), (B["x"] - 60, B["y"] + B["h"] / 2 - 44)
        if L in ("cycle", "hub"):
            dx, dy = bx - ax, by - ay
            d = math.hypot(dx, dy) or 1
            ra, rb = A["w"] / 2 + 12, B["w"] / 2 + 20
            return (ax + dx / d * ra, ay + dy / d * ra), (bx - dx / d * rb, by - dy / d * rb)
        if abs(by - ay) > abs(bx - ax) * 0.6:
            return ((ax, A["y"] + A["h"] + 6), (bx, B["y"] - 14)) if by > ay else ((ax, A["y"] - 6), (bx, B["y"] + B["h"] + 14))
        return ((A["x"] + A["w"] + 6, ay), (B["x"] - 14, by)) if bx > ax else ((A["x"] - 6, ay), (B["x"] + B["w"] + 14, by))

    def draw_connector(self, A, B, tl, t, L):
        g, pal, dna = self.g, self.pal, self.dna
        start = max(A["t"], B["t"]) + 0.05
        prog = e_io((tl - start) / 0.55)
        if prog <= 0:
            return
        (ax, ay), (bx, by) = self.anchors(A, B, L)
        style = dna["connector"]
        vertical = abs(by - ay) >= abs(bx - ax)
        if style == "straight" or L in ("steps", "hub"):
            pts = densify([(ax, ay), (bx, by)])
        elif style == "elbow":
            if vertical:
                my = (ay + by) / 2
                pts = densify([(ax, ay), (ax, my), (bx, my), (bx, by)])
            else:
                mx = (ax + bx) / 2
                pts = densify([(ax, ay), (mx, ay), (mx, by), (bx, by)])
        elif L == "cycle":
            cx, cy = STAGE[0] + STAGE[2] / 2, STAGE[1] + STAGE[3] / 2
            m = ((ax + bx) / 2, (ay + by) / 2)
            out = (m[0] - cx, m[1] - cy)
            dd = math.hypot(*out) or 1
            ctrl = (m[0] + out[0] / dd * 80, m[1] + out[1] / dd * 80)
            pts = bezier((ax, ay), ctrl, ctrl, (bx, by))
        elif vertical:
            pts = bezier((ax, ay), (ax, (ay + by) / 2), (bx, (ay + by) / 2), (bx, by))
        else:
            pts = bezier((ax, ay), ((ax + bx) / 2, ay), ((ax + bx) / 2, by), (bx, by))
        col = mix(pal["text"], pal["accents"][0], 0.35)
        part = trim(pts, prog)
        if style == "flow":
            g.poly(part, mix(pal["bg"], col, 0.35), 1, 9)
            g.poly(part, col, 1, 4, dash=(14, 12), phase=-t * 80)
        else:
            g.poly(part, col, 1, 4.5)
        tip, prev = part[-1], part[-2] if len(part) > 1 else part[-1]
        ang = math.atan2(tip[1] - prev[1], tip[0] - prev[0])
        if prog >= 0.98:
            g.poly([(tip[0] - 20 * math.cos(ang - 0.5), tip[1] - 20 * math.sin(ang - 0.5)), tip,
                    (tip[0] - 20 * math.cos(ang + 0.5), tip[1] - 20 * math.sin(ang + 0.5))], col, 1, 5)
            u = (t * 0.6 + (A["x"] * 0.37 + B["y"] * 0.11) * 0.01) % 1.0      # travelling data packet
            px, py = trim(pts, u)[-1]
            g.circle(px, py, 9, pal["accents"][1])
            g.ring(px, py, 10 + 12 * u, pal["accents"][1], 0.7 * (1 - u), 3)
        else:
            g.circle(tip[0], tip[1], 9, pal["accents"][1])

    def draw_node(self, nd, p, tl, t, L, i):
        g, pal, dna = self.g, self.pal, self.dna
        it = nd["item"]
        sc_, dx, dy, a, sx = entrance(dna, p)
        x, y, w, h = nd["x"], nd["y"], nd["w"], nd["h"]
        cx, cy = x + w / 2, y + h / 2
        k = self.k
        c = g.c
        c.save()
        c.translate((cx + dx) * k, (cy + dy) * k)
        c.scale(sc_ * sx, sc_)
        c.translate(-cx * k, -cy * k)
        if dna["entrance"] == "grow" and p < 1:
            c.clipRect(skia.Rect.MakeXYWH((x - 40) * k, (y - 40) * k, (w + 80) * e_out(p) * k, (h + 400) * k))
        acc = nd["acc"]
        surf = pal["surface"]
        label, sub, icon = str(it.get("label", "")), str(it.get("sub", "") or ""), it.get("icon")
        if icon not in ICONS:
            icon = None
        tfont, bfont, mfont = g.fonts
        txt = pal["text"]
        local = tl - nd["t"]
        if nd.get("emph") is not None and tl >= nd["emph"]:     # emphasis pulse when the narration stresses it
            e = clamp((tl - nd["emph"]) / 0.3)
            pulse = 0.5 + 0.5 * math.sin((tl - nd["emph"]) * 6)
            if nd.get("round"):
                g.ring(cx, cy, w / 2 + 12 + 6 * pulse, acc, e, 5)
            else:
                c.drawPath(g.shape_path(x - 9 - 3 * pulse, y - 9 - 3 * pulse, w + 18 + 6 * pulse, h + 18 + 6 * pulse), g.stroke(acc, e, 5))
        if nd.get("round"):
            r = w / 2
            ux, uy = g.ext_vec()
            dd = g.ext_depth()
            for st in range(4, 0, -1):
                g.circle(cx + ux * dd * st / 4, cy + uy * dd * st / 4, r, g.side_col(acc), a)
            hub = nd.get("hub")
            g.circle(cx, cy, r, acc if hub else surf, a)
            g.ring(cx, cy, r, acc, a, 5, sweep=360 * e_out(local / 0.7))
            if hub:
                g.ring(cx, cy, r + 26 + 8 * math.sin(t * 3), acc, 0.5 * a, 3)
            g.icon(icon or ICONS[(i * 7) % len(ICONS)], cx, cy - (24 if hub else 0), r * (0.62 if hub else 0.8), pal["bg"] if hub else acc, a)
            if hub:
                g.text(label, cx, cy + r * 0.5, g.fit(label, tfont, 36, w - 50), pal["bg"], tfont, "center", a, depth=2, ex=mix(acc, (0, 0, 0), 0.45))
            else:
                g.text(label, cx, cy + r + 50, g.fit(label, tfont, 38, w + 90), txt, tfont, "center", a, depth=3, ex=acc)
                if sub:
                    g.text(sub, cx, cy + r + 88, g.fit(sub, bfont, 27, w + 110), pal["muted"], bfont, "center", a)
        elif nd.get("terminal"):
            self.draw_terminal(nd, tl, a)
        elif nd.get("definition"):
            g.card(x, y, w, h, surf, a, acc)
            term = label or "Definition"
            size = g.fit(term, tfont, 100, w - 90)
            g.text(term, x + 44, y + 150, size, acc, tfont, a=a, depth=6, ex=mix(acc, (0, 0, 0), 0.5))
            g.c.drawRect(skia.Rect.MakeXYWH((x + 46) * k, (y + 188) * k, 180 * e_out((local - 0.2) / 0.7) * k, 8 * k), g.fill(acc, a))
            lines = g.wrap(sub, bfont, 42, w - 90, 6)
            total_w = sum(len(ln.split()) for ln in lines)
            shown = int(total_w * clamp((local - 0.3) / 1.8)) + 1
            cnt = 0
            for li, ln in enumerate(lines):
                lw = ln.split()
                vis = " ".join(lw[:max(0, shown - cnt)])
                cnt += len(lw)
                g.text(vis, x + 44, y + 275 + li * 58, 42, txt, bfont, a=a)
        elif nd.get("big"):
            g.card(x, y, w, h, surf, a, acc)
            val = str(it.get("value") or label)
            num = "".join(ch for ch in val if ch.isdigit() or ch == ".").strip(".")
            shown, pct = val, "%" in val
            if num and num.count(".") <= 1:
                target = float(num)
                cur = target * e_out((local - 0.1) / 1.4)
                fmt = f"{cur:.1f}" if "." in num else (f"{int(round(cur)):,}" if "," in val else f"{int(round(cur))}")
                shown = val.replace(num, fmt, 1) if num in val else fmt
                if pct:
                    g.ring(cx, y + 230, 150, mix(surf, acc, 0.25), a, 24)
                    g.ring(cx, y + 230, 150, acc, a, 24, sweep=360 * min(1, cur / 100))
            if pct:
                g.text(shown, cx, y + 258, g.fit(shown, tfont, 78, 240), txt, tfont, "center", a, depth=5, ex=acc)
            else:
                for j in range(3):          # expanding burst rings behind the counter
                    rr = 60 + ((local * 90 + j * 70) % 210)
                    g.ring(cx, y + 210, rr, acc, a * 0.35 * (1 - (rr - 60) / 210), 3)
                g.text(shown, cx, y + 260, g.fit(shown, tfont, 150, w - 100), acc, tfont, "center", a, depth=9, ex=mix(acc, (0, 0, 0), 0.5))
            if it.get("value"):
                g.text(label, cx, y + 450, g.fit(label, tfont, 46, w - 80), txt, tfont, "center", a, depth=3, ex=acc)
            if sub:
                g.text(sub, cx, y + 505, g.fit(sub, bfont, 28, w - 80), pal["muted"], bfont, "center", a)
        elif nd.get("mini"):
            g.card(x, y, w, h, surf, a, acc)
            c.drawRect(skia.Rect.MakeXYWH(x * k, y * k, w * k, 8 * k), g.fill(acc, a)) if dna["shape"] in ("sharp", "cut") else None
            g.icon(icon or ICONS[(i * 5 + 3) % len(ICONS)], cx, y + 66, 64, acc, a)
            g.text(label, cx, y + 152, g.fit(label, tfont, 38, w - 30), txt, tfont, "center", a, depth=3, ex=acc)
            if sub:
                g.text(sub, cx, y + 188, g.fit(sub, bfont, 22, w - 30), pal["muted"], bfont, "center", a)
        else:
            g.card(x, y, w, h, surf, a, acc)
            if nd.get("funnel"):
                c.drawPath(g.shape_path(x, y, 14, h, "sharp"), g.fill(acc, a))
            pad = 34
            ix = x + pad
            if nd.get("badge"):
                bx = x - 60
                g.circle(bx, cy, 40, acc, a)
                g.text(str(nd["badge"]), bx, cy + 15, 40, pal["bg"], tfont, "center", a)
            if L == "bars":
                val = it.get("value")
                v = self._num(val)
                vmax = max([self._num(n2["item"].get("value")) for n2 in nd["sib"]] + [1e-9])
                frac = clamp(v / vmax) * e_out((local - 0.1) / 1.0)
                track = w - 2 * pad
                c.drawPath(g.shape_path(x + pad, y + h - 52, track, 28, "pill"), g.fill(mix(surf, txt, 0.08), a))
                c.drawPath(g.shape_path(x + pad, y + h - 52, max(28, track * frac), 28, "pill"), g.fill(acc, a))
                g.text(str(val), x + w - pad, y + 72, 50, acc, tfont, "right", a, depth=4, ex=mix(acc, (0, 0, 0), 0.5))
                g.text(label, ix, y + 72, g.fit(label, tfont, 46, w - 300), txt, tfont, a=a, depth=3, ex=acc)
            elif L == "compare":
                left, right = str(it.get("left") or sub), str(it.get("right") or it.get("value") or "")
                g.text(label.upper(), cx, y + 50, g.fit(label.upper(), mfont, 28, w - 60), pal["muted"], mfont, "center", a)
                g.text(left, x + w / 4, y + h - 34, g.fit(left, tfont, 46, w / 2 - 50), pal["accents"][0], tfont, "center", a, depth=3, ex=mix(pal["accents"][0], (0, 0, 0), 0.5))
                g.text(right, x + 3 * w / 4, y + h - 34, g.fit(right, tfont, 46, w / 2 - 50), pal["accents"][1], tfont, "center", a, depth=3, ex=mix(pal["accents"][1], (0, 0, 0), 0.5))
                g.poly([(cx, y + 60), (cx, y + h - 16)], mix(surf, txt, 0.2), a, 2)
            else:
                tile = nd.get("tile")
                ic = icon or ICONS[(i * 5) % len(ICONS)]
                if tile:
                    g.circle(x + 86, y + 90, 58, mix(surf, acc, 0.22), a)
                    g.icon(ic, x + 86, y + 90, 76, acc, a)
                    if L == "pipeline":
                        g.text(f"{i + 1:02d}", x + w - 30, y + 70, 30, mix(surf, acc, 0.7), mfont, "right", a)
                    ty, tx, maxw = y + 215, x + pad, w - 2 * pad
                else:
                    ir = min(52, h * 0.32)
                    g.circle(x + 30 + ir, cy, ir, mix(surf, acc, 0.22), a)
                    g.icon(ic, x + 30 + ir, cy, ir * 1.3, acc, a)
                    tx = x + 60 + 2 * ir
                    maxw = x + w - tx - pad
                    ty = cy - (4 if sub else -16)
                size = g.fit(label, tfont, 50, maxw)
                g.text(label, tx, ty, size, txt, tfont, a=a, depth=3, ex=acc)
                if sub:
                    for li, ln in enumerate(g.wrap(sub, bfont, 31, maxw, 3 if tile else 2)):
                        g.text(ln, tx, ty + 48 + li * 38, 31, pal["muted"], bfont, a=a)
                if L == "timeline":
                    lx = DW / 2
                    g.circle(lx, cy, 16, acc, a)
                    g.ring(lx, cy, 28 + 4 * math.sin(t * 3 + i), acc, a * 0.6, 3)
                    if it.get("value"):
                        side_l = nd.get("side") == "L"
                        g.text(str(it["value"]), (x + w + 70) if side_l else (x - 70), cy + 12, 32, acc, mfont,
                               "left" if side_l else "right", a)
                if L == "stack" and i == len(nd["sib"]) - 1 and local > 0.6:
                    g.c.drawPath(g.shape_path(x + w - 160, y - 22, 130, 44, "pill"), g.fill(acc, e_out(local - 0.6)))
                    g.text("TOP", x + w - 95, y + 10, 26, pal["bg"], mfont, "center", e_out(local - 0.6))
        c.restore()

    @staticmethod
    def _num(v):
        try:
            return float(str(v).replace("%", "").replace(",", "").replace("$", "").split()[0])
        except Exception:
            return 0.0

    def draw_terminal(self, nd, tl, a):
        g, pal = self.g, self.pal
        x, y, w, h = nd["x"], nd["y"], nd["w"], nd["h"]
        k = self.k
        dark = (14, 16, 22) if not pal["light"] else (28, 30, 38)
        g.card(x, y, w, h, dark, a, pal["accents"][0])
        for j, cc in enumerate(((255, 95, 87), (255, 189, 46), (39, 201, 63))):
            g.circle(x + 40 + j * 34, y + 40, 10, cc, a)
        title = nd["item"].get("label", "")
        g.text(title, x + w / 2, y + 50, 24, (150, 155, 170), g.fonts[2], "center", a)
        lines = nd["item"].get("lines") or []
        mfont = g.fonts[2]
        prev_end = nd["t"] + 0.3
        for j, ln in enumerate(lines):
            st = nd["line_t"][j] if j < len(nd.get("line_t", [])) and nd["line_t"][j] is not None else prev_end
            st = max(st, prev_end)
            dur = max(0.35, len(ln) * 0.028)
            prev_end = st + dur
            lt = tl - st
            if lt <= 0:
                break
            n = int(len(ln) * clamp(lt / dur))
            vis = ln[:n]
            size = g.fit(ln, mfont, 40, w - 90)
            comment = ln.strip().startswith(("#", "//", "--"))
            colr = pal["accents"][2] if comment else ((230, 232, 240) if j % 2 == 0 else pal["accents"][0])
            g.text(vis, x + 40, y + 132 + j * 76, size, colr, mfont, a=a)
            last = j == len(lines) - 1 or tl < prev_end
            if n < len(ln) or (last and int(tl * 2.5) % 2 == 0):
                cw = g.width(vis, mfont, size)
                g.c.drawRect(skia.Rect.MakeXYWH((x + 44 + cw) * k, (y + 98 + j * 76) * k, 16 * k, 36 * k), g.fill(pal["accents"][0], a))

    # ---------------------------------------------------------------- hook / captions / transitions / end
    def draw_hook(self, s, tl):
        g, pal = self.g, self.pal
        hook = s["data"].get("hook") or self.sc.get("hook") or s["data"].get("title", "")
        parts, bold = [], False
        for chunk in hook.split("**"):
            for w in chunk.split():
                parts.append((w, bold))
            bold = not bold
        tfont = g.fonts[0]
        size = 124
        while True:
            lines, cur, cw = [], [], 0
            for w, b in parts:
                ww = g.width(w, tfont, size)
                if cur and cw + ww > 940:
                    lines.append(cur)
                    cur, cw = [], 0
                cur.append((w, b, ww))
                cw += ww + 28
            lines.append(cur)
            if len(lines) <= 4 or size <= 70:
                break
            size -= 8
        y0 = 1000 - len(lines) * size * 0.58
        n = 0
        for j in range(6):   # primitive burst behind the hook
            u = e_out((tl - 0.05 - j * 0.07) / 0.9)
            ang = j * 1.047 + 0.3
            r = 140 + 460 * u
            px, py = 540 + math.cos(ang) * r, 960 + math.sin(ang) * r * 1.3
            colr = pal["accents"][j % 4]
            if j % 3 == 0:
                g.ring(px, py, 30 - 12 * u, colr, 1, 6)
            elif j % 3 == 1:
                g.circle(px, py, 16 - 6 * u, colr)
            else:
                rr = 26 - 8 * u
                g.poly([(px + rr * math.cos(u * 4 + q * 2.094), py + rr * math.sin(u * 4 + q * 2.094)) for q in range(3)], colr, 1, 5, close=True)
        for li, ln in enumerate(lines):
            x = 70
            for (w, b, ww) in ln:
                u = e_back((tl - 0.05 - n * 0.08) / 0.42)
                if u > 0:
                    yy = y0 + li * size * 1.16 + 60 * (1 - u)
                    if b:
                        g.card(x - 14, yy - size * 0.86, max(1, (ww + 28) * clamp(u)), size * 1.1, pal["accents"][0], 1, pal["accents"][0], depth=14)
                    g.text(w, x, yy, size, pal["bg"] if b else pal["text"], tfont, a=clamp(u), depth=0 if b else 10, ex=pal["accents"][1])
                x += ww + 28
                n += 1

    def draw_captions(self, s, tl):
        g, pal = self.g, self.pal
        if s["data"]["layout"] == "hook":
            return                      # the hook text itself is on screen
        cur = None
        ch = s["chunks"]
        for i, chunk in enumerate(ch):
            end = ch[i + 1][0][1] if i + 1 < len(ch) else chunk[-1][2] + 0.5
            if chunk[0][1] - 0.05 <= tl < end:
                cur = chunk
                break
        if not cur:
            return
        style = self.dna["caption"]
        size, y = 52, 1720
        font = g.fonts[0]
        sp = 18
        widths = [g.width(w[0], font, size) for w in cur]
        total = sum(widths) + sp * (len(cur) - 1)
        if total > 960:
            size = int(size * 960 / total)
            widths = [g.width(w[0], font, size) for w in cur]
            total = sum(widths) + sp * (len(cur) - 1)
        x = DW / 2 - total / 2
        k = self.k
        if style == "pill":
            g.c.drawPath(g.shape_path(x - 34, y - size - 12, total + 68, size + 42, "pill"), g.fill(pal["surface"]))
        for wi, ((wd, s0, s1), ww) in enumerate(zip(cur, widths)):
            nxt = cur[wi + 1][1] if wi + 1 < len(cur) else s1 + 0.3
            active = s0 - 0.03 <= tl < nxt
            colr = pal["text"] if tl >= s0 - 0.03 else pal["muted"]
            if active:
                acc = pal["accents"][0]
                if style == "boxed":
                    g.c.drawPath(g.shape_path(x - 10, y - size - 4, ww + 20, size + 26, "rounded"), g.fill(acc))
                    colr = pal["bg"]
                elif style == "underline":
                    g.c.drawRect(skia.Rect.MakeXYWH(x * k, (y + 12) * k, ww * k, 8 * k), g.fill(acc))
                else:
                    colr = acc
            g.text(wd, x, y, size, colr, font)
            x += ww + sp

    def draw_transition(self, t):
        g, pal, dna = self.g, self.pal, self.dna
        for i, s in enumerate(self.scenes[1:], start=1):
            d = t - s["start"]
            if -0.28 <= d <= 0.28:
                u = (d + 0.28) / 0.56            # cover until 0.5, then uncover
                cov = e_io(u * 2) if u < 0.5 else 1 - e_io((u - 0.5) * 2)
                c1, c2 = pal["accents"][i % 4], pal["accents"][(i + 1) % 4]
                W, H = self.w, self.h
                style = dna["transition"]
                if style == "wipe_h":
                    x0 = 0 if u < 0.5 else W * (1 - cov)
                    g.c.drawRect(skia.Rect.MakeXYWH(x0, 0, W * cov, H), g.fill(c1))
                elif style == "wipe_v":
                    y0 = 0 if u < 0.5 else H * (1 - cov)
                    g.c.drawRect(skia.Rect.MakeXYWH(0, y0, W, H * cov), g.fill(c1))
                elif style == "diagonal":
                    edge = (W + H) * cov
                    p = skia.Path()
                    if u < 0.5:
                        p.moveTo(0, 0); p.lineTo(edge, 0); p.lineTo(edge - H, H); p.lineTo(0, H)
                    else:
                        p.moveTo(W, 0); p.lineTo(W - edge + H, 0); p.lineTo(W - edge, H); p.lineTo(W, H)
                    p.close()
                    g.c.drawPath(p, g.fill(c1))
                elif style == "iris":
                    g.c.drawCircle(W / 2, H / 2, math.hypot(W, H) / 2 * cov, g.fill(c1))
                elif style == "blinds":
                    nb = 8
                    for b in range(nb):
                        ub = clamp(cov * 1.4 - b * 0.05)
                        g.c.drawRect(skia.Rect.MakeXYWH(0, b * H / nb, W, H / nb * ub + 1), g.fill(c1 if b % 2 else c2))
                else:  # split
                    g.c.drawRect(skia.Rect.MakeXYWH(0, 0, W, H / 2 * cov + 1), g.fill(c1))
                    g.c.drawRect(skia.Rect.MakeXYWH(0, H - H / 2 * cov, W, H / 2 * cov), g.fill(c2))

    def draw_end(self, t):
        g, pal = self.g, self.pal
        u = (t - (self.total - 2.6)) / 0.5
        if u <= 0:
            return
        cov = e_out(u)
        g.c.drawRect(skia.Rect.MakeXYWH(0, 0, self.w, self.h * cov), g.fill(pal["bg"]))
        if cov < 0.95:
            return
        a = e_out(u - 0.3)
        acc = pal["accents"][0]
        for j in range(4):
            g.ring(540, 820, 150 + j * 40 + 20 * math.sin(t * 2 + j), pal["accents"][j % 4], a * (0.6 - j * 0.12), 4)
        g.circle(540, 820, 130 * e_back(u - 0.3), acc)
        g.text((self.handle.lstrip("@")[:1] or "D").upper(), 540, 866, 130, pal["bg"], g.fonts[0], "center", a)
        g.text(self.handle or "", 540, 1060, 58, pal["text"], g.fonts[0], "center", e_out(u - 0.5), depth=6, ex=acc)
        g.text("One concept. Every day.", 540, 1120, 32, pal["muted"], g.fonts[1], "center", e_out(u - 0.6))
        b = e_back(u - 0.75)
        if b > 0:
            wbtn = 330 * b
            g.c.drawPath(g.shape_path(540 - wbtn / 2, 1170, wbtn, 96, "pill"), g.fill(pal["accents"][1]))
            g.text("Follow", 540, 1234, 44, pal["bg"], g.fonts[0], "center", clamp(b))


def render(video, audio_path, out_path, log=print):
    n = int(math.ceil(video.total * video.fps))
    cmd = [ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgra", "-s", f"{video.w}x{video.h}",
           "-r", str(video.fps), "-i", "-", "-i", str(audio_path), "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
           "-pix_fmt", "yuv420p", "-rc-lookahead", "20", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
           "-movflags", "+faststart", "-shortest", str(out_path)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    t0 = time.time()
    try:
        for f in range(n):
            proc.stdin.write(video.frame(f / video.fps).data)
            if f % (video.fps * 15) == 0:
                log(f"  frame {f}/{n} ({time.time() - t0:.0f}s)")
    finally:
        proc.stdin.close()
        proc.wait()
    if proc.returncode:
        raise RuntimeError("ffmpeg failed")
    log(f"  rendered {n} frames in {time.time() - t0:.0f}s")


def stills(video, times, pattern):
    for i, t in enumerate(times):
        video.frame(t)
        video.surface.makeImageSnapshot().save(pattern % i, skia.kPNG)


import d3  # noqa: E402  (3D scenes; imported last because d3 uses the helpers above)
