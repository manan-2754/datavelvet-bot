"""
3D explainer engine - renders a storyboard (list of scenes) into a vertical 4K video.

Style: minimal dark "engineering explainer" - numbered section kicker, title,
rotating 3D wireframe objects, a system bar, resource chips and an info card
that fills row by row while the narrator speaks.

All layout is designed on a 1080x1920 canvas and scaled to the output size,
so the same storyboard renders at 1080p (fast preview) or 2160x3840 (4K).
Frames are drawn with Skia and piped straight into ffmpeg.
"""
import math
import subprocess
import time
from functools import lru_cache
from pathlib import Path

import numpy as np
import skia

BASE_W, BASE_H = 1080, 1920
FONT_DIR = Path(__file__).parent / "assets" / "fonts"

BG = (10, 10, 11)
WHITE = (240, 240, 240)
GREY = (120, 120, 124)
DIM = (70, 70, 74)
CARD = (24, 24, 26)
CARD_EDGE = (40, 40, 44)
PILL = (30, 30, 33)

TRANSITION = 0.5  # seconds for scene crossfades

SANS = "Inter-Medium"
SANS_REG = "Inter-Regular"
SANS_BOLD = "Inter-SemiBold"
MONO = "JetBrainsMono-Regular"
MONO_BOLD = "JetBrainsMono-SemiBold"


def ffmpeg_exe():
    import shutil
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def ease(x):
    x = clamp(x)
    return 1 - (1 - x) ** 3


def ease_io(x):
    x = clamp(x)
    return 3 * x * x - 2 * x * x * x


@lru_cache(maxsize=None)
def typeface(name):
    return skia.Typeface.MakeFromFile(str(FONT_DIR / f"{name}.ttf"))


@lru_cache(maxsize=None)
def shape_geometry(shape):
    """Polylines (lists of xyz points) in unit space (~[-1, 1]) for each 3D wireframe shape."""
    lines = []

    def box(x0, y0, z0, x1, y1, z1):
        v = [(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
        edges = [(0, 1), (0, 2), (0, 4), (1, 3), (1, 5), (2, 3), (2, 6), (3, 7), (4, 5), (4, 6), (5, 7), (6, 7)]
        return [[v[a], v[b]] for a, b in edges]

    def ring(y, r, n=28):
        return [[(r * math.cos(2 * math.pi * i / n), y, r * math.sin(2 * math.pi * i / n)) for i in range(n + 1)]]

    if shape == "stack":
        for i in range(3):
            y0 = -0.9 + i * 0.62
            lines += box(-0.9, y0, -0.7, 0.9, y0 + 0.48, 0.7)
    elif shape == "cylinder":
        lines += ring(-0.85, 0.8) + ring(0.0, 0.8) + ring(0.85, 0.8)
        for ang in (0, 90, 180, 270):
            a = math.radians(ang)
            lines.append([(0.8 * math.cos(a), -0.85, 0.8 * math.sin(a)), (0.8 * math.cos(a), 0.85, 0.8 * math.sin(a))])
    elif shape == "sphere":
        n = 32
        for tilt in (0, 60, 120):
            t = math.radians(tilt)
            pts = []
            for i in range(n + 1):
                a = 2 * math.pi * i / n
                x, y = math.cos(a), math.sin(a)
                pts.append((x * math.cos(t), y, x * math.sin(t)))
            lines.append(pts)
        lines += ring(0.0, 1.0, n)
    elif shape == "pyramid":
        b = [(-0.9, 0.8, -0.9), (0.9, 0.8, -0.9), (0.9, 0.8, 0.9), (-0.9, 0.8, 0.9)]
        top = (0, -0.95, 0)
        for i in range(4):
            lines.append([b[i], b[(i + 1) % 4]])
            lines.append([b[i], top])
    elif shape == "panel":
        lines += box(-1.0, -0.7, -0.12, 1.0, 0.7, 0.12)
        for i in range(3):
            y = -0.35 + i * 0.3
            lines.append([(-0.7, y, -0.13), (0.4 if i == 2 else 0.7, y, -0.13)])
    elif shape == "phone":
        lines += box(-0.5, -0.95, -0.1, 0.5, 0.95, 0.1)
        lines.append([(-0.15, 0.78, -0.11), (0.15, 0.78, -0.11)])
    else:  # cube
        lines += box(-0.8, -0.8, -0.8, 0.8, 0.8, 0.8)
    return lines


SHAPES = ("cube", "stack", "cylinder", "sphere", "pyramid", "panel", "phone")
ICONS = ("cpu", "ram", "disk", "net", "db", "lock", "user", "file", "cloud", "gear")


class Renderer:
    def __init__(self, width=2160, height=3840, fps=30, handle=""):
        self.w, self.h, self.fps = width, height, fps
        self.k = width / BASE_W  # design-unit -> pixel scale
        self.handle = handle
        info = skia.ImageInfo.Make(width, height, skia.kBGRA_8888_ColorType, skia.kPremul_AlphaType)
        self.buf = np.zeros((height, width, 4), np.uint8)
        self.surface = skia.Surface.MakeRasterDirect(info, self.buf)
        self.c = self.surface.getCanvas()
        self._text_cache = {}

    # ---------- primitives (all coordinates in design units) ----------
    def color(self, rgb, a=1.0):
        return skia.Color(int(rgb[0]), int(rgb[1]), int(rgb[2]), int(255 * clamp(a)))

    def fill_paint(self, rgb, a=1.0):
        return skia.Paint(AntiAlias=True, Color=self.color(rgb, a))

    def stroke_paint(self, rgb, a=1.0, width=1.5, dash=None):
        p = skia.Paint(AntiAlias=True, Color=self.color(rgb, a), Style=skia.Paint.kStroke_Style,
                       StrokeWidth=width * self.k, StrokeCap=skia.Paint.kRound_Cap)
        if dash:
            p.setPathEffect(skia.DashPathEffect.Make([d * self.k for d in dash], 0))
        return p

    def rrect(self, x, y, w, h, r, fill=None, a=1.0, edge=None, edge_a=1.0, dash=None, edge_w=1.5):
        k = self.k
        rr = skia.RRect.MakeRectXY(skia.Rect.MakeXYWH(x * k, y * k, w * k, h * k), r * k, r * k)
        if fill is not None and a > 0:
            self.c.drawRRect(rr, self.fill_paint(fill, a))
        if edge is not None and edge_a > 0:
            self.c.drawRRect(rr, self.stroke_paint(edge, edge_a, edge_w, dash))

    def line(self, x0, y0, x1, y1, rgb, a=1.0, width=1.5, dash=None):
        if a <= 0:
            return
        k = self.k
        self.c.drawLine(x0 * k, y0 * k, x1 * k, y1 * k, self.stroke_paint(rgb, a, width, dash))

    def circle(self, cx, cy, r, fill=None, a=1.0, edge=None, edge_a=1.0, edge_w=1.5):
        k = self.k
        if fill is not None and a > 0:
            self.c.drawCircle(cx * k, cy * k, r * k, self.fill_paint(fill, a))
        if edge is not None and edge_a > 0:
            self.c.drawCircle(cx * k, cy * k, r * k, self.stroke_paint(edge, edge_a, edge_w))

    def text_image(self, text, font_name, size, rgb):
        """Text is rasterised once and cached as an image - ~50x faster than drawing glyphs every frame."""
        key = (text, font_name, size, rgb)
        img = self._text_cache.get(key)
        if img is None:
            font = skia.Font(typeface(font_name), size * self.k)
            font.setSubpixel(True)
            metrics = font.getMetrics()
            width = max(1, int(math.ceil(font.measureText(text))) + 4)
            height = max(1, int(math.ceil(metrics.fDescent - metrics.fAscent)) + 4)
            surf = skia.Surface(width, height)
            cv = surf.getCanvas()
            cv.clear(skia.ColorTRANSPARENT)
            cv.drawString(text, 2, 2 - metrics.fAscent, font, skia.Paint(AntiAlias=True, Color=self.color(rgb)))
            img = (surf.makeImageSnapshot(), -metrics.fAscent + 2)
            if len(self._text_cache) > 4000:
                self._text_cache.clear()
            self._text_cache[key] = img
        return img

    def text_width(self, text, font_name, size):
        return skia.Font(typeface(font_name), size).measureText(text)

    def text(self, text, x, y, font_name=SANS, size=30, rgb=WHITE, a=1.0, align="left", blur=0.0):
        """Draw text with its baseline at y (design units)."""
        if not text or a <= 0.003:
            return
        img, ascent = self.text_image(text, font_name, size, tuple(rgb))
        w_design = img.width() / self.k
        if align == "center":
            x -= w_design / 2
        elif align == "right":
            x -= w_design
        paint = skia.Paint(Alphaf=clamp(a))
        if blur > 0.05:
            paint.setImageFilter(skia.ImageFilters.Blur(blur * self.k, blur * self.k))
        self.c.drawImage(img, x * self.k, y * self.k - ascent, skia.SamplingOptions(skia.FilterMode.kLinear), paint)

    def fit_size(self, text, font_name, size, max_w, min_ratio=0.6):
        s = size
        while s > size * min_ratio and self.text_width(text, font_name, s) > max_w:
            s -= 1
        return s

    def rich_text(self, text, cx, y, size, a):
        """Centered mono line where **word** is drawn bright."""
        parts, bold = [], False
        for chunk in text.split("**"):
            if chunk:
                parts.append((chunk, bold))
            bold = not bold
        widths = [self.text_width(p, MONO_BOLD if b else MONO, size) for p, b in parts]
        x = cx - sum(widths) / 2
        for (p, b), w in zip(parts, widths):
            self.text(p, x, y, MONO_BOLD if b else MONO, size, WHITE if b else GREY, a)
            x += w

    # ---------- 3D wireframes ----------
    def wireframe(self, shape, cx, cy, size, t, a=1.0, active=False, seed=0.0):
        if a <= 0.01:
            return
        yaw = t * 0.45 + seed
        pitch = math.radians(-22)
        cyaw, syaw, cp, sp = math.cos(yaw), math.sin(yaw), math.cos(pitch), math.sin(pitch)
        cam = 4.2
        k = self.k
        col = WHITE if active else (200, 200, 205)
        for poly in shape_geometry(shape if shape in SHAPES else "cube"):
            pts, depth = [], 0.0
            for x, y, z in poly:
                x, z = x * cyaw - z * syaw, x * syaw + z * cyaw
                y, z = y * cp - z * sp, y * sp + z * cp
                f = cam / (cam + z)
                pts.append(((cx + x * size * f) * k, (cy + y * size * f) * k))
                depth += z
            depth /= len(poly)
            shade = clamp(0.75 - depth * 0.35, 0.25, 1.0)
            path = skia.Path()
            path.moveTo(*pts[0])
            for p in pts[1:]:
                path.lineTo(*p)
            self.c.drawPath(path, self.stroke_paint(col, a * shade * (1.0 if active else 0.75), 1.6, dash=(2.5, 4.5)))
        if active:
            pulse = 0.5 + 0.5 * math.sin(t * 3)
            glow = skia.Paint(AntiAlias=True, Color=self.color(WHITE, a * (0.15 + 0.15 * pulse)))
            glow.setMaskFilter(skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, 14 * k))
            self.c.drawCircle(cx * k, cy * k, size * 0.35 * k, glow)
            self.circle(cx, cy, 5, fill=WHITE, a=a * 0.9)

    # ---------- icons ----------
    def icon(self, kind, cx, cy, s, a):
        g = (215, 215, 220)
        k = self.k
        if kind == "cpu":
            self.rrect(cx - s * 0.32, cy - s * 0.32, s * 0.64, s * 0.64, 3, edge=g, edge_a=a, edge_w=1.6)
            self.rrect(cx - s * 0.14, cy - s * 0.14, s * 0.28, s * 0.28, 2, fill=g, a=a)
            for i in (-1, 0, 1):
                o = i * s * 0.18
                for d in (1, -1):
                    self.line(cx + o, cy + d * s * 0.32, cx + o, cy + d * s * 0.46, g, a, 1.4)
                    self.line(cx + d * s * 0.32, cy + o, cx + d * s * 0.46, cy + o, g, a, 1.4)
        elif kind == "ram":
            self.rrect(cx - s * 0.42, cy - s * 0.2, s * 0.84, s * 0.4, 3, edge=g, edge_a=a, edge_w=1.6)
            for i in range(4):
                x = cx - s * 0.3 + i * s * 0.2
                self.rrect(x - s * 0.05, cy - s * 0.1, s * 0.1, s * 0.14, 1, fill=g, a=a)
        elif kind == "disk":
            self.rrect(cx - s * 0.32, cy - s * 0.38, s * 0.64, s * 0.76, 5, edge=g, edge_a=a, edge_w=1.6)
            self.circle(cx, cy - s * 0.04, s * 0.16, edge=g, edge_a=a, edge_w=1.6)
            self.circle(cx, cy - s * 0.04, s * 0.04, fill=g, a=a)
        elif kind == "net":
            self.circle(cx, cy, s * 0.36, edge=g, edge_a=a, edge_w=1.6)
            self.line(cx - s * 0.36, cy, cx + s * 0.36, cy, g, a, 1.4)
            oval = skia.Rect.MakeXYWH((cx - s * 0.15) * k, (cy - s * 0.36) * k, s * 0.3 * k, s * 0.72 * k)
            self.c.drawOval(oval, self.stroke_paint(g, a, 1.4))
        elif kind == "db":
            for yy in (-0.28, 0.0, 0.28):
                oval = skia.Rect.MakeXYWH((cx - s * 0.32) * k, (cy + s * yy - s * 0.09) * k, s * 0.64 * k, s * 0.18 * k)
                self.c.drawOval(oval, self.stroke_paint(g, a, 1.4))
            self.line(cx - s * 0.32, cy - s * 0.28, cx - s * 0.32, cy + s * 0.28, g, a, 1.4)
            self.line(cx + s * 0.32, cy - s * 0.28, cx + s * 0.32, cy + s * 0.28, g, a, 1.4)
        elif kind == "lock":
            self.rrect(cx - s * 0.3, cy - s * 0.05, s * 0.6, s * 0.42, 4, edge=g, edge_a=a, edge_w=1.6)
            arc = skia.Rect.MakeXYWH((cx - s * 0.18) * k, (cy - s * 0.38) * k, s * 0.36 * k, s * 0.5 * k)
            self.c.drawArc(arc, 180, 180, False, self.stroke_paint(g, a, 1.6))
        elif kind == "user":
            self.circle(cx, cy - s * 0.14, s * 0.14, edge=g, edge_a=a, edge_w=1.6)
            arc = skia.Rect.MakeXYWH((cx - s * 0.3) * k, (cy + s * 0.06) * k, s * 0.6 * k, s * 0.5 * k)
            self.c.drawArc(arc, 180, 180, False, self.stroke_paint(g, a, 1.6))
        elif kind == "file":
            self.rrect(cx - s * 0.26, cy - s * 0.36, s * 0.52, s * 0.72, 3, edge=g, edge_a=a, edge_w=1.6)
            for i in range(3):
                yy = cy - s * 0.14 + i * s * 0.14
                self.line(cx - s * 0.14, yy, cx + s * 0.14, yy, g, a, 1.3)
        elif kind == "cloud":
            for ox, oy, r in ((-0.16, 0.04, 0.17), (0.04, -0.08, 0.22), (0.2, 0.06, 0.15)):
                self.circle(cx + ox * s, cy + oy * s, r * s, edge=g, edge_a=a, edge_w=1.5)
        else:  # gear / generic
            self.circle(cx, cy, s * 0.24, edge=g, edge_a=a, edge_w=1.6)
            for i in range(8):
                ang = i * math.pi / 4
                self.line(cx + math.cos(ang) * s * 0.26, cy + math.sin(ang) * s * 0.26,
                          cx + math.cos(ang) * s * 0.38, cy + math.sin(ang) * s * 0.38, g, a, 2.0)

    # ---------- components ----------
    def pill_width(self, text, font=MONO, size=19, icon=None):
        return self.text_width(text, font, size) + 36 + (28 if icon else 0)

    def pill(self, text, cx, cy, a, font=MONO, size=19, active=False, icon=None):
        w = self.pill_width(text, font, size, icon)
        x = cx - w / 2
        self.rrect(x, cy - 19, w, 38, 19, fill=WHITE if active else PILL, a=a * (0.95 if active else 0.9),
                   edge=CARD_EDGE, edge_a=0 if active else a)
        tx = x + 18
        if icon:
            self.icon(icon, tx + 8, cy, 22, a * 0.8)
            tx += 28
        self.text(text, tx, cy + size * 0.36, font, size, (15, 15, 15) if active else (200, 200, 205), a)
        return w

    def draw_tabs(self, tabs, y, a):
        items = tabs.get("items", [])[:4]
        active = tabs.get("active", -1)
        labels = [f"{i + 1} · {t}" for i, t in enumerate(items)]
        widths = [self.pill_width(l, MONO, 18) for l in labels]
        gap = 14
        x = BASE_W / 2 - (sum(widths) + gap * (len(widths) - 1)) / 2
        for i, (l, w) in enumerate(zip(labels, widths)):
            self.pill(l, x + w / 2, y, a, size=18, active=(i == active))
            x += w + gap

    @staticmethod
    def node_xs(n):
        if n <= 0:
            return []
        if n == 1:
            return [BASE_W / 2]
        span = {2: 440, 3: 640}.get(n, 780)
        return [BASE_W / 2 - span / 2 + i * span / (n - 1) for i in range(n)]

    def node_box(self, x, a):
        self.rrect(x - 110, 505, 220, 205, 16, edge=(90, 90, 95), edge_a=a * 0.8, dash=(4, 5))

    def draw_node(self, node, x, t, a_shape, a_text, idx):
        self.wireframe(node.get("shape", "cube"), x, 600, 52, t, a_shape, node.get("active", False), seed=idx * 1.3)
        label = node.get("label", "")
        self.text(label, x, 698, SANS, self.fit_size(label, SANS, 30, 210), WHITE, a_text, "center")
        if node.get("sub"):
            self.text(node["sub"], x, 728, MONO, self.fit_size(node["sub"], MONO, 18, 220), GREY, a_text, "center")
        if node.get("tag"):
            self.pill(node["tag"], x, 768, a_text, size=17)

    def draw_bar(self, bar, t, a):
        x, y, w, h = 150, 830, 780, 84
        self.rrect(x, y, w, h, h / 2, fill=PILL, a=a, edge=CARD_EDGE, edge_a=a)
        self.circle(x + 44, y + h / 2, 26, fill=(40, 40, 44), a=a)
        self.wireframe("sphere", x + 44, y + h / 2, 15, t * 1.4, a * 0.9)
        size = self.fit_size(bar.get("text", ""), MONO, 34, w - 260)
        self.text(bar.get("text", ""), x + 88, y + h / 2 + size * 0.36, MONO, size, WHITE, a)
        if bar.get("tag"):
            tw = self.pill_width(bar["tag"], SANS, 19)
            self.pill(bar["tag"], x + w - 22 - tw / 2, y + h / 2, a, font=SANS, size=19, active=True)

    @staticmethod
    def chip_centers(n):
        sq, gap, ggap = 54, 10, 34
        gw = 3 * sq + 2 * gap
        x = BASE_W / 2 - (n * gw + (n - 1) * ggap) / 2
        return [x + gw / 2 + i * (gw + ggap) for i in range(n)]

    def draw_chips(self, chips, a):
        groups = chips[:4]
        sq, gap, ggap = 54, 10, 34
        gw = 3 * sq + 2 * gap
        total = len(groups) * gw + (len(groups) - 1) * ggap
        x = BASE_W / 2 - total / 2
        for g in groups:
            for i in range(3):
                sx = x + i * (sq + gap)
                self.rrect(sx, 972, sq, sq, 9, fill=(34, 34, 37), a=a, edge=(60, 60, 64), edge_a=a)
                self.icon(g.get("icon", "gear"), sx + sq / 2, 972 + sq / 2, sq * 0.9, a)
            self.text(g.get("label", ""), x + gw / 2, 1060, MONO, 18, GREY, a, "center")
            x += gw + ggap

    def draw_connectors(self, n_nodes, n_chips, a):
        for x in self.node_xs(n_nodes):
            self.line(x, 790, x, 828, DIM, a, 1.4, dash=(2, 5))
        if n_chips:
            for x in self.chip_centers(min(n_chips, 4)):
                self.line(x, 916, x, 968, DIM, a, 1.4, dash=(2, 5))

    def draw_card_frame(self, card, a):
        self.rrect(90, 1150, 900, 420, 28, fill=CARD, a=a * 0.97, edge=CARD_EDGE, edge_a=a)
        self.text(card.get("title", ""), 126, 1205, SANS_BOLD, 26, WHITE, a)
        if card.get("note"):
            self.text(card["note"], 954, 1203, MONO, 18, GREY, a, "right")

    def draw_card_row(self, i, row, a, reveal):
        y = 1262 + i * 54
        a2 = a * ease(reveal)
        if a2 <= 0.003:
            return
        dx = (1 - ease(reveal)) * 18
        self.circle(140, y - 8, 14, fill=(44, 44, 48), a=a2)
        self.text(str(i + 1), 140, y - 1, MONO_BOLD, 15, (210, 210, 210), a2, "center")
        key, val = (list(row) + ["", ""])[:2]
        self.text(key, 172 + dx, y, MONO, self.fit_size(key, MONO, 18, 190), GREY, a2)
        self.text(val, 380 + dx, y, SANS_REG, self.fit_size(val, SANS_REG, 26, 570, 0.55), WHITE, a2)

    def draw_card_bars(self, bars, start_row, a, local):
        top = 1262 + start_row * 54
        maxv = max([abs(b.get("value", 0)) for b in bars] + [1e-9])
        for i, b in enumerate(bars[:3]):
            y = top + i * 58
            a2 = a * ease(clamp((local - 0.4 - i * 0.6) / 0.6))
            if a2 <= 0.003:
                continue
            grow = ease_io(clamp((local - 0.6 - i * 0.6) / 1.2))
            self.text(b.get("label", ""), 126, y, SANS_REG, self.fit_size(b.get("label", ""), SANS_REG, 22, 280), (215, 215, 215), a2)
            full = 380
            v = abs(b.get("value", 0))
            self.rrect(420, y - 16, full, 12, 6, fill=(44, 44, 48), a=a2)
            self.rrect(420, y - 16, max(12, full * v / maxv * grow), 12, 6, fill=WHITE, a=a2)
            shown = b.get("value", 0) * grow
            whole = float(b.get("value", 0)).is_integer() or abs(b.get("value", 0)) >= 10
            num = f"{shown:.0f}" if whole else f"{shown:.1f}"
            self.text(f"{num} {b.get('unit', '')}".strip(), 954, y, MONO, 20, WHITE, a2, "right")

    def draw_card_notes(self, notes, a):
        x = 126
        for n in notes[:3]:
            w = self.pill_width(n, MONO, 16)
            self.pill(n, x + w / 2, 1530, a, size=16)
            x += w + 12

    def draw_card_contents(self, card, local, dur, prev_card, a=1.0):
        rows = card.get("rows", [])[:5]
        old_rows = prev_card.get("rows", []) if prev_card else []
        new_idx = [i for i, r in enumerate(rows) if not (i < len(old_rows) and old_rows[i] == r)]
        span = max(0.8, (dur - 1.2) * 0.75)
        for i, row in enumerate(rows):
            if i in new_idx:
                at = 0.35 + span * new_idx.index(i) / max(1, len(new_idx))
                self.draw_card_row(i, row, a, (local - at) / 0.45)
            else:
                self.draw_card_row(i, row, a, 1)
        if card.get("bars"):
            same_bars = prev_card is not None and prev_card.get("bars") == card["bars"]
            self.draw_card_bars(card["bars"], len(rows), a, 99 if same_bars else local)
        if card.get("notes"):
            same_notes = prev_card is not None and prev_card.get("notes") == card["notes"]
            self.draw_card_notes(card["notes"], a * (1.0 if same_notes else ease((local - 1.0) / 0.5)))

    # ---------- frame ----------
    def frame(self, timeline, t, total):
        self.c.clear(self.color(BG))
        idx = 0
        for i, sc in enumerate(timeline):
            if t >= sc["start"]:
                idx = i
        cur = timeline[idx]
        prev = timeline[idx - 1] if idx > 0 else None
        local = t - cur["start"]
        e = ease(local / TRANSITION) if prev else ease(local / 0.6)

        def xfade(key, draw):
            """Unchanged component -> drawn steady; changed -> old fades out while new fades in."""
            if prev is not None and prev.get(key) == cur.get(key):
                if cur.get(key):
                    draw(cur[key], 1.0, 0)
                return
            if prev is not None and prev.get(key) and e < 1:
                draw(prev[key], 1 - e, -10 * e)
            if cur.get(key):
                draw(cur[key], e, 10 * (1 - e))

        xfade("kicker_full", lambda v, a, dy: self.text(v, BASE_W / 2, 250 + dy, MONO, 22, GREY, a, "center"))
        xfade("title", lambda v, a, dy: self.text(v, BASE_W / 2, 330 + dy, SANS, self.fit_size(v, SANS, 46, 960, 0.62),
                                                  WHITE, a, "center", blur=(1 - a) * 8))
        xfade("tabs", lambda v, a, dy: self.draw_tabs(v, 400, a))
        xfade("pill", lambda v, a, dy: self.pill(v, BASE_W / 2, 470 + dy, a, font=SANS_REG, size=19, icon="user"))

        # nodes: a node that persists between scenes keeps spinning in place (or glides to its new slot)
        cn = cur.get("nodes") or []
        pn = (prev.get("nodes") or []) if prev else []
        boxed_c = bool(cur.get("boxed"))
        boxed_p = bool(prev.get("boxed")) if prev else False
        cxs, pxs = self.node_xs(len(cn)), self.node_xs(len(pn))

        def ident(n):
            return (n.get("label"), n.get("shape", "cube"))

        prev_ids = {ident(n): (i, n) for i, n in enumerate(pn)}
        cur_ids = {ident(n) for n in cn}
        for i, n in enumerate(cn):
            if prev is None or ident(n) not in prev_ids:
                a = ease(clamp((local - i * 0.12) / 0.6))
                if boxed_c:
                    self.node_box(cxs[i], a)
                self.draw_node(n, cxs[i], t, a, a, i)
                continue
            pi, pnode = prev_ids[ident(n)]
            x = pxs[pi] + (cxs[i] - pxs[pi]) * ease_io(local / 0.7)
            box_a = (e if boxed_c else 0) + ((1 - e) if boxed_p else 0)
            if box_a > 0:
                self.node_box(x, box_a)
            if pnode == n:
                self.draw_node(n, x, t, 1, 1, i)
            else:
                self.draw_node(n, x, t, 1, e, i)
                self.draw_node(pnode, x, t, 0, 1 - e, i)
        for i, n in enumerate(pn):
            if ident(n) not in cur_ids and e < 1:
                if boxed_p:
                    self.node_box(pxs[i], 1 - e)
                self.draw_node(n, pxs[i], t, 1 - e, 1 - e, i)
        vs_now = len(cn) == 2 and cur.get("vs")
        vs_prev = prev is not None and len(pn) == 2 and prev.get("vs")
        if vs_now:
            self.text("VS", BASE_W / 2, 615, SANS_BOLD, 34, GREY, 1 if vs_prev else e, "center")
        elif vs_prev and e < 1:
            self.text("VS", BASE_W / 2, 615, SANS_BOLD, 34, GREY, 1 - e, "center")

        if cur.get("bar"):
            steady = prev is not None and prev.get("bar") and len(pn) == len(cn) and prev.get("chips") == cur.get("chips")
            self.draw_connectors(len(cn), len(cur.get("chips") or []), 1.0 if steady else e)
        xfade("bar", lambda v, a, dy: self.draw_bar(v, t, a))
        xfade("chips", lambda v, a, dy: self.draw_chips(v, a))
        xfade("caption", lambda v, a, dy: self.rich_text(v, BASE_W / 2, 1112, 20, a))

        # card: same title -> frame stays and only the new rows animate in
        cc, pc = cur.get("card"), (prev.get("card") if prev else None)
        keep = bool(cc and pc and pc.get("title") == cc.get("title") and pc.get("note") == cc.get("note"))
        if pc and not keep and e < 1:
            self.draw_card_frame(pc, 1 - e)
            self.draw_card_contents(pc, 99, 1, pc, 1 - e)
        if cc:
            self.draw_card_frame(cc, 1.0 if keep else e)
            self.draw_card_contents(cc, local, cur["dur"], pc if keep else None)

        if self.handle:
            self.text(self.handle, 1010, 160, MONO_BOLD, 18, WHITE, 0.45, "right")
        self.rrect(0, 1912, BASE_W * clamp(t / total), 8, 0, fill=WHITE, a=0.5)

        fade = min(clamp(t / 0.35), clamp((total - t) / 0.5))
        if fade < 1:
            self.c.drawRect(skia.Rect.MakeWH(self.w, self.h), self.fill_paint(BG, 1 - fade))
        return self.buf


def build_timeline(scenes, durations):
    """Attach start/dur to scenes and auto-number the section kickers (00 · ..., 01 · ...)."""
    timeline, t, n, last = [], 0.0, -1, None
    for sc, d in zip(scenes, durations):
        k = sc.get("kicker", "")
        if k != last:
            n += 1
            last = k
        item = dict(sc)
        item["kicker_full"] = f"{n:02d} · {k}" if k else ""
        item["start"], item["dur"] = t, d
        timeline.append(item)
        t += d
    return timeline, t


def render_video(scenes, durations, audio_path, out_path, width=2160, height=3840, fps=30, handle="", log=print):
    timeline, total = build_timeline(scenes, durations)
    r = Renderer(width, height, fps, handle)
    n_frames = int(math.ceil(total * fps))
    cmd = [ffmpeg_exe(), "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "bgra", "-s", f"{width}x{height}", "-r", str(fps), "-i", "-",
           "-i", str(audio_path),
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-rc-lookahead", "20",
           "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
           "-movflags", "+faststart", "-shortest", str(out_path)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    t0 = time.time()
    try:
        for f in range(n_frames):
            proc.stdin.write(r.frame(timeline, f / fps, total).data)
            if f % (fps * 15) == 0:
                log(f"  frame {f}/{n_frames} ({time.time() - t0:.0f}s elapsed)")
    finally:
        proc.stdin.close()
        proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed with code {proc.returncode}")
    log(f"  rendered {n_frames} frames in {time.time() - t0:.0f}s")
    return total


def render_still(scenes, scene_index, at, out_png, width=1080, height=1920, handle=""):
    """Render one frame to PNG (for quick visual checks)."""
    durations = [6.0] * len(scenes)
    timeline, total = build_timeline(scenes, durations)
    r = Renderer(width, height, 30, handle)
    r.frame(timeline, timeline[scene_index]["start"] + at, total)
    r.surface.makeImageSnapshot().save(str(out_png), skia.kPNG)
