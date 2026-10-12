"""
Presentation-style carousels (slide decks), deliberately unlike the 3D Reels: gradient editorial themes with two accent
colours, a hand-drawn icon set, icon tiles, rating meters with a winner badge, myth/fact stamps, a step flow diagram,
an agenda and an illustrated summary, with a deck footer (brand, page number, progress bar) on every slide.
Pure 2D (Pillow) - fast and cheap to make in the cloud.
"""
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

import covers

W, H, M = 1080, 1350, 80
THEMES = {   # bg gradient top/bottom, card, ink, soft text, line, accent 1, accent 2
    "sunset": {"bg": ((255, 238, 226), (255, 218, 232)), "card": (255, 255, 255), "ink": (44, 20, 56), "soft": (110, 84, 118),
               "line": (240, 206, 214), "a1": (124, 58, 237), "a2": (249, 115, 22)},
    "ocean": {"bg": ((7, 42, 66), (13, 95, 120)), "card": (17, 66, 94), "ink": (240, 250, 255), "soft": (170, 210, 225),
              "line": (36, 96, 124), "a1": (94, 234, 212), "a2": (253, 164, 108)},
    "lime": {"bg": ((18, 20, 24), (34, 38, 48)), "card": (40, 45, 56), "ink": (244, 246, 250), "soft": (170, 176, 190),
             "line": (58, 64, 78), "a1": (190, 242, 100), "a2": (167, 139, 250)},
    "candy": {"bg": ((242, 236, 255), (255, 236, 246)), "card": (255, 255, 255), "ink": (32, 27, 78), "soft": (100, 92, 140),
              "line": (226, 214, 246), "a1": (236, 72, 153), "a2": (59, 130, 246)},
    "forest": {"bg": ((234, 244, 230), (215, 234, 210)), "card": (255, 255, 255), "ink": (18, 42, 26), "soft": (70, 100, 78),
               "line": (200, 224, 196), "a1": (22, 163, 74), "a2": (234, 88, 12)},
}
ICONS = ["wifi", "battery", "lock", "phone", "laptop", "chip", "cloud", "globe", "bolt", "shield", "signal", "database",
         "clock", "eye", "key", "gauge", "gear", "download", "warning", "qr", "check", "brain"]
RED, GREEN = (225, 50, 70), (22, 160, 90)


def F(size, kind="head"):
    return covers._font(size, kind)


def fit(d, text, width, lines, start, kind="head", low=28):
    return covers._fit(d, str(text or ""), width, lines, start, kind, low)


def block(d, lines, f, x, y, fill, gap=1.18):
    return covers._text_block(d, lines, f, x, y, fill, gap)


def light(t):
    return t["bg"][0][0] > 128


def icon(d, name, cx, cy, s, col, w=None):
    """A small hand-drawn icon set (lines and shapes) centred on (cx, cy), size s."""
    w = w or max(4, int(s * 0.07))
    r = s / 2
    L = lambda pts: d.line(pts, fill=col, width=w, joint="curve")
    if name == "wifi":
        for k in (1.0, 0.68, 0.36):
            rr = r * k
            d.arc([cx - rr, cy - rr + r * 0.45, cx + rr, cy + rr + r * 0.45], 225, 315, fill=col, width=w)
        d.ellipse([cx - w, cy + r * 0.38, cx + w, cy + r * 0.38 + 2 * w], fill=col)
    elif name == "battery":
        d.rounded_rectangle([cx - r, cy - r * 0.5, cx + r * 0.8, cy + r * 0.5], 8, outline=col, width=w)
        d.rectangle([cx + r * 0.8, cy - r * 0.2, cx + r, cy + r * 0.2], fill=col)
        d.rectangle([cx - r * 0.8, cy - r * 0.3, cx + r * 0.2, cy + r * 0.3], fill=col)
    elif name == "lock":
        d.rounded_rectangle([cx - r * 0.7, cy - r * 0.1, cx + r * 0.7, cy + r * 0.8], 10, fill=col)
        d.arc([cx - r * 0.45, cy - r * 0.8, cx + r * 0.45, cy + r * 0.1], 180, 360, fill=col, width=w)
        L([(cx - r * 0.45, cy - r * 0.35), (cx - r * 0.45, cy - r * 0.1)]); L([(cx + r * 0.45, cy - r * 0.35), (cx + r * 0.45, cy - r * 0.1)])
    elif name == "phone":
        d.rounded_rectangle([cx - r * 0.5, cy - r, cx + r * 0.5, cy + r], 14, outline=col, width=w)
        d.ellipse([cx - w, cy + r * 0.7, cx + w, cy + r * 0.7 + 2 * w], fill=col)
    elif name == "laptop":
        d.rounded_rectangle([cx - r * 0.75, cy - r * 0.7, cx + r * 0.75, cy + r * 0.3], 8, outline=col, width=w)
        L([(cx - r, cy + r * 0.55), (cx + r, cy + r * 0.55)])
    elif name == "chip":
        d.rectangle([cx - r * 0.55, cy - r * 0.55, cx + r * 0.55, cy + r * 0.55], outline=col, width=w)
        d.rectangle([cx - r * 0.22, cy - r * 0.22, cx + r * 0.22, cy + r * 0.22], fill=col)
        for k in (-0.3, 0, 0.3):
            for a, b in (((cx + k * r, cy - r * 0.55), (cx + k * r, cy - r)), ((cx + k * r, cy + r * 0.55), (cx + k * r, cy + r)),
                         ((cx - r * 0.55, cy + k * r), (cx - r, cy + k * r)), ((cx + r * 0.55, cy + k * r), (cx + r, cy + k * r))):
                L([a, b])
    elif name == "cloud":
        for (x, y, rr) in ((-0.35, 0.1, 0.38), (0.05, -0.15, 0.48), (0.42, 0.12, 0.34)):
            d.ellipse([cx + x * r - rr * r, cy + y * r - rr * r, cx + x * r + rr * r, cy + y * r + rr * r], fill=col)
        d.rectangle([cx - r * 0.7, cy + r * 0.05, cx + r * 0.75, cy + r * 0.47], fill=col)
    elif name == "globe":
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=col, width=w)
        d.ellipse([cx - r * 0.45, cy - r, cx + r * 0.45, cy + r], outline=col, width=w)
        L([(cx - r, cy), (cx + r, cy)])
    elif name == "bolt":
        d.polygon([(cx + r * 0.15, cy - r), (cx - r * 0.55, cy + r * 0.15), (cx - r * 0.05, cy + r * 0.15), (cx - r * 0.2, cy + r),
                   (cx + r * 0.55, cy - r * 0.15), (cx + r * 0.05, cy - r * 0.15)], fill=col)
    elif name == "shield":
        d.polygon([(cx, cy - r), (cx + r * 0.8, cy - r * 0.6), (cx + r * 0.65, cy + r * 0.35), (cx, cy + r),
                   (cx - r * 0.65, cy + r * 0.35), (cx - r * 0.8, cy - r * 0.6)], outline=col, width=w)
        L([(cx - r * 0.3, cy), (cx - r * 0.05, cy + r * 0.28), (cx + r * 0.38, cy - r * 0.25)])
    elif name == "signal":
        for k in range(4):
            x = cx - r + k * r * 0.55
            d.rounded_rectangle([x, cy + r - (k + 1) * r * 0.45, x + r * 0.35, cy + r], 4, fill=col)
    elif name == "database":
        for k in (-0.6, 0, 0.6):
            d.ellipse([cx - r * 0.75, cy + k * r - r * 0.25, cx + r * 0.75, cy + k * r + r * 0.25], outline=col, width=w)
        L([(cx - r * 0.75, cy - r * 0.6), (cx - r * 0.75, cy + r * 0.6)]); L([(cx + r * 0.75, cy - r * 0.6), (cx + r * 0.75, cy + r * 0.6)])
    elif name == "clock":
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=col, width=w)
        L([(cx, cy), (cx, cy - r * 0.6)]); L([(cx, cy), (cx + r * 0.45, cy + r * 0.2)])
    elif name == "eye":
        d.chord([cx - r, cy - r * 0.7, cx + r, cy + r * 0.7], 200, 340, outline=col, width=w)
        d.chord([cx - r, cy - r * 0.7, cx + r, cy + r * 0.7], 20, 160, outline=col, width=w)
        d.ellipse([cx - r * 0.3, cy - r * 0.3, cx + r * 0.3, cy + r * 0.3], fill=col)
    elif name == "key":
        d.ellipse([cx - r, cy - r * 0.45, cx - r * 0.1, cy + r * 0.45], outline=col, width=w)
        L([(cx - r * 0.1, cy), (cx + r, cy)]); L([(cx + r * 0.6, cy), (cx + r * 0.6, cy + r * 0.35)]); L([(cx + r * 0.9, cy), (cx + r * 0.9, cy + r * 0.3)])
    elif name == "gauge":
        d.arc([cx - r, cy - r, cx + r, cy + r], 180, 360, fill=col, width=w)
        L([(cx, cy), (cx + r * 0.6, cy - r * 0.6)])
        d.ellipse([cx - w * 1.4, cy - w * 1.4, cx + w * 1.4, cy + w * 1.4], fill=col)
    elif name == "gear":
        for k in range(8):
            a = k * math.pi / 4
            L([(cx + math.cos(a) * r * 0.55, cy + math.sin(a) * r * 0.55), (cx + math.cos(a) * r, cy + math.sin(a) * r)])
        d.ellipse([cx - r * 0.65, cy - r * 0.65, cx + r * 0.65, cy + r * 0.65], outline=col, width=w)
        d.ellipse([cx - r * 0.22, cy - r * 0.22, cx + r * 0.22, cy + r * 0.22], fill=col)
    elif name == "download":
        L([(cx, cy - r), (cx, cy + r * 0.3)]); L([(cx - r * 0.45, cy - r * 0.15), (cx, cy + r * 0.3), (cx + r * 0.45, cy - r * 0.15)])
        L([(cx - r * 0.8, cy + r * 0.8), (cx + r * 0.8, cy + r * 0.8)])
    elif name == "warning":
        d.polygon([(cx, cy - r), (cx + r, cy + r * 0.8), (cx - r, cy + r * 0.8)], outline=col, width=w)
        L([(cx, cy - r * 0.35), (cx, cy + r * 0.25)]); d.ellipse([cx - w, cy + r * 0.45, cx + w, cy + r * 0.45 + 2 * w], fill=col)
    elif name == "qr":
        for x, y in ((-1, -1), (0.2, -1), (-1, 0.2)):
            d.rectangle([cx + x * r, cy + y * r, cx + (x + 0.8) * r, cy + (y + 0.8) * r], outline=col, width=w)
            d.rectangle([cx + (x + 0.25) * r, cy + (y + 0.25) * r, cx + (x + 0.55) * r, cy + (y + 0.55) * r], fill=col)
        for x, y in ((0.3, 0.3), (0.7, 0.3), (0.3, 0.7), (0.7, 0.7), (0.5, 0.5)):
            d.rectangle([cx + x * r - r * 0.1, cy + y * r - r * 0.1, cx + x * r + r * 0.1, cy + y * r + r * 0.1], fill=col)
    elif name == "check":
        L([(cx - r * 0.6, cy), (cx - r * 0.15, cy + r * 0.5), (cx + r * 0.65, cy - r * 0.45)])
    elif name == "x":
        L([(cx - r * 0.55, cy - r * 0.55), (cx + r * 0.55, cy + r * 0.55)]); L([(cx + r * 0.55, cy - r * 0.55), (cx - r * 0.55, cy + r * 0.55)])
    elif name == "brain":
        for (x, y) in ((-0.35, -0.3), (0.35, -0.3), (-0.4, 0.3), (0.4, 0.3)):
            d.ellipse([cx + x * r - r * 0.45, cy + y * r - r * 0.42, cx + x * r + r * 0.45, cy + y * r + r * 0.42], outline=col, width=w)
        L([(cx, cy - r * 0.7), (cx, cy + r * 0.7)])
    else:
        d.ellipse([cx - r * 0.5, cy - r * 0.5, cx + r * 0.5, cy + r * 0.5], fill=col)


def pick_icon(text, i=0):
    """Icon from the slide's words when the writer did not name one."""
    low = str(text).lower()
    for keys, name in ((("wi-fi", "wifi", "router", "band"), "wifi"), (("battery", "charg", "mah"), "battery"),
                       (("password", "lock", "encrypt", "privacy"), "lock"), (("phone", "mobile"), "phone"),
                       (("laptop", "computer", "pc"), "laptop"), (("cpu", "chip", "processor", "nand", "flash"), "chip"),
                       (("cloud", "server"), "cloud"), (("internet", "web", "dns", "site"), "globe"),
                       (("speed", "fast", "latency"), "gauge"), (("power", "energy"), "bolt"), (("secur", "safe", "shield"), "shield"),
                       (("signal", "5g", "4g", "network"), "signal"), (("data", "storage", "disk", "drive"), "database"),
                       (("time", "hour", "cycle"), "clock"), (("qr", "code"), "qr"), (("ai", "model", "learn"), "brain"),
                       (("key", "login", "2fa"), "key"), (("risk", "fire", "danger", "damage"), "warning")):
        if any(k in low for k in keys):
            return name
    return ["gear", "bolt", "globe", "chip", "clock", "eye"][i % 6]


class Deck:
    def __init__(self, content, fmt, theme=None, badge=""):
        self.c, self.fmt = content, fmt
        self.tname = theme or random.choice(list(THEMES))
        self.t = THEMES[self.tname]
        self.a1, self.a2 = (self.t["a1"], self.t["a2"]) if random.random() < 0.6 else (self.t["a2"], self.t["a1"])
        self.badge = badge
        self.slides = []
        self.total = len(content["slides"]) + (2 if fmt == "versus" else 3)   # title, [agenda], N content, summary
        self.seed = random.randrange(1 << 30)

    def background(self):
        t = self.t
        top, bot = t["bg"]
        g = Image.linear_gradient("L").resize((W, H))
        img = Image.composite(Image.new("RGB", (W, H), bot), Image.new("RGB", (W, H), top), g)
        blobs = Image.new("RGB", (W, H), (0, 0, 0))
        bd = ImageDraw.Draw(blobs)
        rng = random.Random(self.seed + len(self.slides))
        mask = Image.new("L", (W, H), 0)
        md = ImageDraw.Draw(mask)
        for col in (self.a1, self.a2):                      # two soft colour blobs per slide
            x, y, r = rng.randint(-100, W + 100), rng.randint(-100, H + 100), rng.randint(260, 420)
            bd.ellipse([x - r, y - r, x + r, y + r], fill=col)
            md.ellipse([x - r, y - r, x + r, y + r], fill=70 if light(t) else 55)
        mask = mask.filter(ImageFilter.GaussianBlur(120))
        img = Image.composite(blobs.filter(ImageFilter.GaussianBlur(80)), img, mask)
        d = ImageDraw.Draw(img)
        dot = t["line"]
        for gx in range(W - 300, W - 60, 34):               # dot-grid accent, top right
            for gy in range(60, 260, 34):
                d.ellipse([gx - 3, gy - 3, gx + 3, gy + 3], fill=dot)
        return img, d

    def new(self):
        img, d = self.background()
        n = len(self.slides) + 1
        d.text((M, H - 92), "DATAVELVET", font=F(28, "label"), fill=self.t["soft"])
        d.text((W - M - 90, H - 92), f"{n:02d} / {self.total:02d}", font=F(28, "label"), fill=self.t["soft"])
        d.rounded_rectangle([M, H - 48, W - M, H - 40], 4, fill=self.t["line"])
        d.rounded_rectangle([M, H - 48, M + (W - 2 * M) * n / self.total, H - 40], 4, fill=self.a1)
        return img, d

    def card(self, d, box, outline=None, radius=30):
        x0, y0, x1, y1 = box
        if light(self.t):
            d.rounded_rectangle([x0 + 6, y0 + 12, x1 + 6, y1 + 12], radius, fill=tuple(max(0, c - 22) for c in self.t["bg"][1]))
        d.rounded_rectangle(box, radius, fill=self.t["card"], outline=outline, width=4 if outline else 0)

    def chip(self, d, x, y, text, fill=None, ink=(255, 255, 255), size=30):
        f = F(size, "label")
        w = d.textlength(text, font=f) + 44
        d.rounded_rectangle([x, y, x + w, y + size + 26], (size + 26) // 2, fill=fill or self.a1)
        d.text((x + 22, y + 11), text, font=f, fill=ink)
        return x + w

    def tile(self, d, x, y, s, name, fill, num=None):
        d.rounded_rectangle([x, y, x + s, y + s], int(s * 0.24), fill=fill)
        icon(d, name, x + s / 2, y + s / 2, s * 0.5, (255, 255, 255))
        if num is not None:
            r = s * 0.2
            d.ellipse([x + s - r * 1.4, y - r * 0.6, x + s + r * 0.6, y + r * 1.4], fill=self.t["card"], outline=fill, width=5)
            nf = F(int(r * 1.1), "head")
            d.text((x + s - r * 0.4 - d.textlength(str(num), font=nf) / 2, y + r * 0.4 - nf.size * 0.6), str(num), font=nf, fill=fill)

    def title(self):
        img, d = self.new()
        t = self.t
        cx, cy = W - 300, 400                                   # illustrated composition: rings + icon disc
        for k, col in enumerate((self.a2, self.a1)):
            r = 230 - k * 40
            d.ellipse([cx - r + k * 60, cy - r + k * 30, cx + r + k * 60, cy + r + k * 30], fill=col if k else None,
                      outline=None if k else col, width=10)
        icon(d, self.c.get("icon") or pick_icon(self.c["title"]), cx + 60, cy + 30, 210, (255, 255, 255))
        f, ls = fit(d, self.c["title"], W - 2 * M, 4, 100)
        sf, sl = fit(d, self.c.get("subtitle", ""), W - 2 * M, 2, 38, "body")
        hgt = len(ls) * f.size * 1.06 + 24 + len(sl) * sf.size * 1.18
        y0 = min(790, H - 170 - hgt)
        self.chip(d, M, y0 - 90, self.badge, self.a1)
        y = block(d, ls, f, M, y0, t["ink"], 1.06)
        block(d, sl, sf, M, y + 24, t["soft"])
        d.text((M, 140), "SWIPE  ->", font=F(34, "label"), fill=self.a2)
        self.slides.append(img)

    def agenda(self):
        img, d = self.new()
        t = self.t
        d.text((M, 120), "WHAT'S INSIDE", font=F(34, "label"), fill=self.a1)
        f, ls = fit(d, self.c["title"], W - 2 * M, 2, 58)
        y = block(d, ls, f, M, 180, t["ink"], 1.08) + 50
        for k, s in enumerate(self.c["slides"], 1):
            col = self.a1 if k % 2 else self.a2
            self.card(d, [M, y, W - M, y + 150])
            self.tile(d, M + 26, y + 25, 100, s.get("icon") or pick_icon(s["heading"] + " " + s.get("body", ""), k), col)
            hf, hl = fit(d, s["heading"], W - 2 * M - 270, 2, 40)
            block(d, hl, hf, M + 160, y + 75 - len(hl) * hf.size * 0.58, t["ink"], 1.1)
            nf = F(34, "head")
            d.text((W - M - 70, y + 52), f"{k:02d}", font=nf, fill=col)
            y += 172
        self.slides.append(img)

    def flow(self, active):
        img, d = self.new()
        t = self.t
        n = len(self.c["slides"])
        gap, y0 = 34, 140
        bw = (W - 2 * M - (n - 1) * gap) / n
        for k in range(n):
            x = M + k * (bw + gap)
            on, done = k == active, k < active
            fill = self.a1 if on else (self.a2 if done else t["card"])
            d.rounded_rectangle([x, y0, x + bw, y0 + bw], 26, fill=fill, outline=None if (on or done) else t["line"], width=3)
            s = self.c["slides"][k]
            icon(d, s.get("icon") or pick_icon(s["heading"] + " " + s.get("body", ""), k), x + bw / 2, y0 + bw / 2, bw * 0.48,
                 (255, 255, 255) if (on or done) else t["soft"])
            if k < n - 1:
                ax = x + bw + 5
                d.line([ax, y0 + bw / 2, ax + gap - 10, y0 + bw / 2], fill=t["soft"], width=4)
                d.polygon([(ax + gap - 8, y0 + bw / 2), (ax + gap - 20, y0 + bw / 2 - 10), (ax + gap - 20, y0 + bw / 2 + 10)], fill=t["soft"])
        return img, d, y0 + bw + 80

    def stamp(self, d, cx, cy, r, ok):
        col = GREEN if ok else RED
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)
        d.ellipse([cx - r + 12, cy - r + 12, cx + r - 12, cy + r - 12], outline=(255, 255, 255), width=4)
        icon(d, "check" if ok else "x", cx, cy, r * 1.1, (255, 255, 255), w=14)

    def meter(self, d, x, y, w, score, col):
        score = max(0, min(5, int(round(float(score or 0)))))
        seg = (w - 4 * 10) / 5
        for k in range(5):
            d.rounded_rectangle([x + k * (seg + 10), y, x + k * (seg + 10) + seg, y + 22], 11,
                                fill=col if k < score else self.t["line"])

    def content(self, k, s):
        t = self.t
        ic = s.get("icon") or pick_icon(s["heading"] + " " + s.get("body", ""), k)
        col = self.a1 if k % 2 else self.a2
        if self.fmt == "steps":
            img, d, y = self.flow(k - 1)
            self.chip(d, M, y, f"STEP {k}", self.a1)
            y += 90
        else:
            img, d = self.new()
            y = 120
        if self.fmt == "versus":
            self.chip(d, M, y, f"ROUND {k} / {len(self.c['slides'])}", col)
            hf, hl = fit(d, s["heading"], W - 2 * M - 180, 2, 72)
            yy = block(d, hl, hf, M, y + 90, t["ink"], 1.06)
            self.tile(d, W - M - 150, y + 70, 150, ic, col)
            y = max(yy, y + 240) + 40
            cw = (W - 2 * M - 30) / 2
            fits = [fit(d, v, cw - 60, 6, 48, "body", 30) for v in (s.get("a"), s.get("b"))]
            ch = max(330, 250 + max(len(fl) * ff.size * 1.3 for ff, fl in fits))
            sa, sb = s.get("score_a"), s.get("score_b")
            for j, (name, val, sc, c2) in enumerate(((self.c.get("a"), s.get("a"), sa, self.a1), (self.c.get("b"), s.get("b"), sb, self.a2))):
                x = M + j * (cw + 30)
                win = sa is not None and sb is not None and ((j == 0 and float(sa) > float(sb)) or (j == 1 and float(sb) > float(sa)))
                self.card(d, [x, y, x + cw, y + ch], outline=c2 if win else None)
                d.rounded_rectangle([x, y, x + cw, y + 104], 30, fill=c2)
                d.rectangle([x, y + 74, x + cw, y + 104], fill=c2)
                nf, nl = fit(d, str(name or "").upper(), cw - 60, 1, 38, "head", 22)
                d.text((x + 30, y + 32), nl[0] if nl else "", font=nf, fill=(255, 255, 255))
                vf, vl = fits[j]
                yb = block(d, vl, vf, x + 30, y + 140, t["ink"], 1.3)
                if sc is not None:
                    self.meter(d, x + 30, yb + 30, cw - 60, sc, c2)
                if win:
                    self.chip(d, x + cw - 190, y + ch - 30, "WINNER", c2, size=26)
            if s.get("body"):
                bf, bl = fit(d, s["body"], W - 2 * M, 3, 38, "body", 28)
                block(d, bl, bf, M, y + ch + 60, t["soft"], 1.3)
            self.slides.append(img)
            return
        if self.fmt == "mythfact":
            myth = str(s.get("verdict", "MYTH")).upper() == "MYTH"
            self.card(d, [M, y, W - M, y + 380], outline=RED if myth else t["line"])
            self.chip(d, M + 40, y + 40, "MYTH" if myth else "SOUNDS LIKE A MYTH...", RED if myth else t["soft"])
            hf, hl = fit(d, s["heading"], W - 2 * M - 300, 3, 60)
            block(d, hl, hf, M + 40, y + 140, t["ink"], 1.1)
            if myth:
                for i, ln in enumerate(hl):
                    ly = y + 140 + i * hf.size * 1.1 + hf.size * 0.55
                    d.line([M + 34, ly, M + 46 + d.textlength(ln, font=hf), ly], fill=RED, width=6)
            self.stamp(d, W - M - 130, y + 200, 95, not myth)
            y += 430
            self.card(d, [M, y, W - M, H - 170], outline=GREEN)
            self.chip(d, M + 40, y + 40, "THE FACT", GREEN)
            self.tile(d, W - M - 170, y + 40, 130, ic, col)
            bf, bl = fit(d, s.get("body", ""), W - 2 * M - 80, 7, 48, "body", 30)
            block(d, bl, bf, M + 40, y + 190, t["ink"], 1.3)
            self.slides.append(img)
            return
        if self.fmt != "steps":
            self.tile(d, M, y, 220, ic, col, num=k)
            hf, hl = fit(d, s["heading"], W - 2 * M - 270, 3, 66)
            block(d, hl, hf, M + 260, y + 110 - len(hl) * hf.size * 0.55, t["ink"], 1.06)
            y += 290
        else:
            hf, hl = fit(d, s["heading"], W - 2 * M - 200, 2, 68)
            yy = block(d, hl, hf, M, y, t["ink"], 1.06)
            self.tile(d, W - M - 150, y - 20, 150, ic, self.a1)
            y = max(yy, y + 150) + 40
        bf, bl = fit(d, s.get("body", ""), W - 2 * M - 100, 8, 48, "body", 30)
        bottom = min(H - 170, y + 100 + len(bl) * bf.size * 1.35)
        self.card(d, [M, y, W - M, bottom])
        d.rounded_rectangle([M, y, M + 16, bottom], 8, fill=col)
        block(d, bl, bf, M + 56, y + 50, t["ink"], 1.35)
        self.illustration(d, ic, bottom + 30, H - 150, col)
        self.slides.append(img)

    def illustration(self, d, ic, top, bottom, col):
        """Fills free space with the slide's icon in a ring-and-dots composition."""
        room = bottom - top
        if room < 220:
            return
        r = min(room * 0.36, 190)
        cx, cy = W / 2 + 120, top + room / 2
        other = self.a2 if col == self.a1 else self.a1
        d.ellipse([cx - r * 1.45, cy - r * 1.45, cx + r * 1.45, cy + r * 1.45], outline=self.t["line"], width=4)
        d.ellipse([cx - r * 1.15 - 70, cy - r * 1.15 + 20, cx + r * 1.15 - 70, cy + r * 1.15 + 20], outline=other, width=8)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)
        icon(d, ic, cx, cy, r * 1.05, (255, 255, 255))
        for k in range(7):
            a = k * 0.9 + 0.4
            px, py = cx + math.cos(a) * r * 1.45, cy + math.sin(a) * r * 1.45
            d.ellipse([px - 9, py - 9, px + 9, py + 9], fill=other if k % 2 else col)

    def summary(self):
        img, d = self.new()
        t = self.t
        self.chip(d, M, 110, "SUMMARY", self.a1)
        f, ls = fit(d, self.c.get("takeaway", ""), W - 2 * M, 3, 56)
        y = block(d, ls, f, M, 200, t["ink"], 1.1) + 50
        if self.fmt == "versus":
            cw = [(W - 2 * M) * 0.36, (W - 2 * M) * 0.32, (W - 2 * M) * 0.32]
            xs = [M, M + cw[0], M + cw[0] + cw[1]]
            d.rounded_rectangle([M, y, W - M, y + 84], 20, fill=t["ink"])
            for j, (h, c2) in enumerate((("", None), (self.c.get("a", ""), self.a1), (self.c.get("b", ""), self.a2))):
                if c2:
                    d.rounded_rectangle([xs[j] + 10, y + 14, xs[j] + 34, y + 38], 6, fill=c2)
                hf, hl = fit(d, str(h).upper(), cw[j] - 70, 1, 28, "label", 18)
                d.text((xs[j] + 44, y + 26), hl[0] if hl else "", font=hf, fill=t["bg"][0])
            y += 96
            for k, s in enumerate(self.c["slides"]):
                self.card(d, [M, y, W - M, y + 112], radius=18)
                sa, sb = s.get("score_a"), s.get("score_b")
                for j, val in enumerate([s["heading"], s.get("a", ""), s.get("b", "")]):
                    vf, vl = fit(d, val, cw[j] - 70, 2, 27, "head" if j == 0 else "body", 18)
                    block(d, vl, vf, xs[j] + 24, y + 22, t["ink"], 1.15)
                if sa is not None and sb is not None and float(sa) != float(sb):
                    j = 1 if float(sa) > float(sb) else 2
                    d.ellipse([xs[j] + cw[j] - 56, y + 34, xs[j] + cw[j] - 12, y + 78], fill=self.a1 if j == 1 else self.a2)
                    icon(d, "check", xs[j] + cw[j] - 34, y + 56, 28, (255, 255, 255), w=6)
                y += 124
        else:
            for k, s in enumerate(self.c["slides"], 1):
                if self.fmt == "mythfact":
                    ok = str(s.get("verdict", "")).upper() != "MYTH"
                    d.ellipse([M, y, M + 72, y + 72], fill=GREEN if ok else RED)
                    icon(d, "check" if ok else "x", M + 36, y + 36, 40, (255, 255, 255), w=8)
                else:
                    self.tile(d, M, y, 72, s.get("icon") or pick_icon(s["heading"] + " " + s.get("body", ""), k), self.a1 if k % 2 else self.a2)
                hf, hl = fit(d, s["heading"], W - 2 * M - 110, 2, 40)
                y = max(block(d, hl, hf, M + 104, y + 12, t["ink"], 1.1), y + 72) + 34
        d.text((M, H - 160), "Save this   ·   Share it   ·   Follow @datavelvet", font=F(32, "label"), fill=self.a2)
        self.slides.append(img)

    def build(self, out_dir):
        self.title()
        if self.fmt != "versus":
            self.agenda()
        for k, s in enumerate(self.c["slides"], 1):
            self.content(k, s)
        self.summary()
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        paths = []
        for k, im in enumerate(self.slides, 1):
            p = out / f"deck_{k:02d}.jpg"
            im.save(p, quality=93)
            paths.append(p)
        return paths
