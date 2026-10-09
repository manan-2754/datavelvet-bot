"""
Holographic 3D diagram scenes (VR look): real 3D objects - server racks, databases, users, globes, chips, phones,
laptops, screens, clouds, locks - rendered as glowing wireframes with dotted hidden edges and scan-line glass faces,
materialising out of a holographic floor. Live flows stream packets along dotted motion connectors, counters update
live, and the camera never stops moving. Ten diagram formats; each video's DNA changes the object primitive, camera
move, holo style and floor, so no two videos look alike.
"""
import math
import random

import skia

from mg import DW, clamp, e_back, e_io, e_out, mix

LAYOUTS3D = ("holo_flow", "holo_hub", "holo_orbit", "holo_layers", "holo_cluster", "holo_pipeline", "holo_tree",
             "holo_chart", "holo_compare", "holo_timeline")
PANEL = (40, 400, 1000, 1250)        # x, y, w, h of the holographic viewport (design units)
F = 1100.0
SIDES = {"tri": 3, "box": 4, "hex": 6, "oct": 8, "round": 20}
HOLO_TEXT = (238, 243, 255)
OBJ_FOR_ICON = {"server": "server", "db": "db", "cloud": "cloud", "lock": "lock", "key": "lock", "shield": "lock",
                "user": "user", "phone": "phone", "laptop": "laptop", "gear": "chip", "cpu": "chip", "globe": "globe",
                "file": "doc", "code": "screen", "search": "screen", "chart": "screen", "layers": "layers"}
HEIGHT = {"server": 1.7, "db": 1.25, "user": 1.3, "cloud": 1.3, "globe": 1.5, "lock": 1.0, "phone": 1.15,
          "laptop": 1.0, "chip": 0.4, "doc": 1.15, "screen": 1.45, "layers": 0.75, "prism": 1.1}
FOOT = {"server": 0.75, "db": 0.65, "user": 0.4, "cloud": 0.8, "globe": 0.75, "lock": 0.5, "phone": 0.4,
        "laptop": 0.8, "chip": 0.75, "doc": 0.5, "screen": 0.8, "layers": 0.8, "prism": 0.65}


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _lerp(a, b, u):
    return (a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u, a[2] + (b[2] - a[2]) * u)


def _num(v):
    try:
        return float(str(v).replace("%", "").replace(",", "").replace("$", "").split()[0])
    except Exception:
        return 0.0


class Cam:
    def __init__(self, yaw, pitch, dist, f, cx, cy, target=(0.0, 0.0, 0.0)):
        self.cyw, self.syw = math.cos(yaw), math.sin(yaw)
        self.cp, self.sp = math.cos(pitch), math.sin(pitch)
        self.dist, self.f, self.cx, self.cy, self.t = dist, f, cx, cy, target
        self.pos = (target[0] - dist * self.cp * self.syw, target[1] + dist * self.sp, target[2] - dist * self.cp * self.cyw)

    def p(self, v):
        x, y, z = v[0] - self.t[0], v[1] - self.t[1], v[2] - self.t[2]
        x1 = x * self.cyw - z * self.syw
        z1 = x * self.syw + z * self.cyw
        y2 = y * self.cp + z1 * self.sp
        z2 = -y * self.sp + z1 * self.cp
        d = max(0.8, z2 + self.dist)
        s = self.f / d
        return (self.cx + x1 * s, self.cy - y2 * s, d, s)


# ---------------------------------------------------------------- meshes (world space)
class Mesh:
    def __init__(self):
        self.faces = []    # (pts, normal, deco polylines)
        self.curves = []   # (pts, centre, closed) - classified front/back per segment
        self.lines = []    # always-front polylines
        self.leds = []     # (point, on)


def _box(m, T, cx, y0, cz, w, h, d, deco=None):
    x0, x1, z0, z1, y1 = cx - w / 2, cx + w / 2, cz - d / 2, cz + d / 2, y0 + h
    P = lambda x, y, z: T((x, y, z))
    m.faces.append(([P(x0, y1, z0), P(x1, y1, z0), P(x1, y1, z1), P(x0, y1, z1)], (0, 1, 0), []))
    m.faces.append(([P(x0, y0, z0), P(x1, y0, z0), P(x1, y1, z0), P(x0, y1, z0)], (0, 0, -1),
                    [[T(q) for q in line] for line in (deco or [])]))
    m.faces.append(([P(x1, y0, z0), P(x1, y0, z1), P(x1, y1, z1), P(x1, y1, z0)], (1, 0, 0), []))
    m.faces.append(([P(x1, y0, z1), P(x0, y0, z1), P(x0, y1, z1), P(x1, y1, z1)], (0, 0, 1), []))
    m.faces.append(([P(x0, y0, z1), P(x0, y0, z0), P(x0, y1, z0), P(x0, y1, z1)], (-1, 0, 0), []))


def _ring(m, T, cx, y, cz, r, n=28):
    m.curves.append(([T((cx + r * math.cos(2 * math.pi * i / n), y, cz + r * math.sin(2 * math.pi * i / n)))
                      for i in range(n)], T((cx, y, cz)), True))


def _cyl(m, T, cx, y0, cz, r, h, bands=()):
    for y in (y0, y0 + h, *bands):
        _ring(m, T, cx, y, cz, r)
    for i in range(8):
        a = 2 * math.pi * i / 8
        x, z = cx + r * math.cos(a), cz + r * math.sin(a)
        m.curves.append(([T((x, y0, z)), T((x, y0 + h, z))], T((cx, y0 + h / 2, cz)), False))


def _sphere(m, T, c, r, t=0.0):
    for k in (-0.55, 0.0, 0.55):
        rr = r * math.sqrt(1 - k * k)
        m.curves.append(([T((c[0] + rr * math.cos(2 * math.pi * i / 28), c[1] + k * r, c[2] + rr * math.sin(2 * math.pi * i / 28)))
                          for i in range(28)], T(c), True))
    for j in range(3):
        a = t * 0.6 + j * math.pi / 3
        m.curves.append(([T((c[0] + r * math.cos(u) * math.cos(a), c[1] + r * math.sin(u), c[2] + r * math.cos(u) * math.sin(a)))
                          for u in [2 * math.pi * i / 28 for i in range(28)]], T(c), True))


def _prism(m, T, cx, cz, y0, r, h, sides, rot=0.0):
    base = [(cx + r * math.cos(rot + 2 * math.pi * i / sides), cz + r * math.sin(rot + 2 * math.pi * i / sides)) for i in range(sides)]
    m.faces.append(([T((x, y0 + h, z)) for x, z in base], (0, 1, 0), []))
    for i in range(sides):
        (xa, za), (xb, zb) = base[i], base[(i + 1) % sides]
        nx, nz = zb - za, -(xb - xa)
        if nx * ((xa + xb) / 2 - cx) + nz * ((za + zb) / 2 - cz) < 0:
            nx, nz = -nx, -nz
        ln = math.hypot(nx, nz) or 1
        m.faces.append(([T((xa, y0, za)), T((xb, y0, zb)), T((xb, y0 + h, zb)), T((xa, y0 + h, za))], (nx / ln, 0, nz / ln), []))


def _rect(x0, y0, x1, y1, z):
    return [(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z), (x0, y0, z)]


def build(kind, x, z, y0=0.0, s=1.0, t=0.0, sides=6, rot=0.0):
    """One holographic object, base centred at (x, y0, z), scaled by s."""
    T = lambda p: (x + p[0] * s, y0 + p[1] * s, z + p[2] * s)
    m = Mesh()
    if kind == "server":
        slots = [_rect(-0.4, y, 0.4, y + 0.3, -0.505) for y in (0.2, 0.67, 1.14)]
        _box(m, T, 0, 0, 0, 1.0, 1.7, 1.0, slots)
        for i, y in enumerate((0.2, 0.67, 1.14)):
            m.leds.append((T((0.28, y + 0.15, -0.51)), math.sin(t * 5 + i * 2.1) > -0.2))
            m.leds.append((T((0.14, y + 0.15, -0.51)), True))
    elif kind == "db":
        _cyl(m, T, 0, 0, 0, 0.62, 1.25, (0.42, 0.84))
    elif kind == "user":
        _cyl(m, T, 0, 0, 0, 0.33, 0.72)
        _sphere(m, T, (0, 1.02, 0), 0.27, t)
    elif kind == "cloud":
        for (cx, cy, cz, r) in ((-0.45, 0.55, 0, 0.42), (0.05, 0.78, 0.05, 0.55), (0.5, 0.52, -0.05, 0.4)):
            _sphere(m, T, (cx, cy, cz), r, t)
    elif kind == "globe":
        _sphere(m, T, (0, 0.75, 0), 0.72, t)
        _ring(m, T, 0, 0.75, 0, 0.95)
    elif kind == "lock":
        _box(m, T, 0, 0, 0, 0.85, 0.65, 0.4, [_rect(-0.06, 0.22, 0.06, 0.42, -0.205)])
        m.lines.append([T((0.27 * math.cos(u), 0.65 + 0.32 * math.sin(u), 0)) for u in [i * math.pi / 14 for i in range(15)]])
    elif kind == "phone":
        _box(m, T, 0, 0, 0, 0.62, 1.15, 0.1, [_rect(-0.26, 0.14, 0.26, 1.04, -0.051), [(-0.06, 0.07, -0.051), (0.06, 0.07, -0.051)]])
    elif kind == "laptop":
        _box(m, T, 0, 0, 0, 1.4, 0.07, 0.95)
        code = [[(-0.55, y, 0.405), (-0.55 + w, y, 0.405)] for y, w in ((0.82, 0.7), (0.66, 0.95), (0.5, 0.55), (0.34, 0.8))]
        _box(m, T, 0, 0.07, 0.44, 1.4, 0.9, 0.06, code)
    elif kind == "chip":
        _box(m, T, 0, 0.05, 0, 1.2, 0.2, 1.2)
        _box(m, T, 0, 0.25, 0, 0.6, 0.1, 0.6)
        for i in range(4):
            o = -0.42 + i * 0.28
            m.lines.append([T((o, 0.1, -0.6)), T((o, 0.1, -0.8))])
            m.lines.append([T((0.6, 0.1, o)), T((0.8, 0.1, o))])
            m.lines.append([T((o, 0.1, 0.6)), T((o, 0.1, 0.8))])
            m.lines.append([T((-0.6, 0.1, o)), T((-0.8, 0.1, o))])
    elif kind == "doc":
        _box(m, T, 0, 0, 0, 0.85, 1.15, 0.07, [[(-0.28, y, -0.036), (0.28 - (0.15 if i == 3 else 0), y, -0.036)]
                                                for i, y in enumerate((0.9, 0.72, 0.54, 0.36))])
    elif kind == "screen":
        _box(m, T, 0, 0, 0, 0.5, 0.05, 0.4)
        _box(m, T, 0, 0.05, 0.05, 0.1, 0.35, 0.1)
        code = [[(-0.6, y, -0.036), (-0.6 + w, y, -0.036)] for y, w in ((1.2, 0.5), (1.05, 0.9), (0.9, 0.7), (0.75, 1.0), (0.6, 0.45))]
        code.append(_rect(-0.69, 0.46, 0.69, 1.34, -0.036))
        _box(m, T, 0, 0.4, 0, 1.5, 1.0, 0.07, code)
    elif kind == "layers":
        for i in range(3):
            _box(m, T, 0, i * 0.32, 0, 1.4, 0.06, 1.05)
    else:
        _prism(m, T, 0, 0, 0, 0.62, 1.1, sides, rot)
    return m


def kind_for(item, sides):
    return OBJ_FOR_ICON.get(item.get("icon"), "prism")


def _clip(a, b, yc):
    if yc is None:
        return a, b
    if a[1] <= yc and b[1] <= yc:
        return a, b
    if a[1] > yc and b[1] > yc:
        return None
    u = (yc - a[1]) / ((b[1] - a[1]) or 1e-9)
    p = _lerp(a, b, u)
    return (a, p) if a[1] <= yc else (p, b)


# ---------------------------------------------------------------- holo renderer
class Holo:
    def __init__(self, v, cam):
        self.v, self.g, self.cam, self.k = v, v.g, cam, v.g.k
        self.pal, self.dna = v.pal, v.dna
        self.bg = holo_bg(v.pal)
        self.style = self.dna["render3d"]
        self.sides = SIDES[self.dna["prim"]]
        self.rot = math.pi / 4 if self.sides == 4 else (math.pi / 2 if self.sides == 3 else 0.0)
        self.labels = []

    def P(self, p):
        q = self.cam.p(p)
        return q[0] * self.k, q[1] * self.k

    def _paint(self, rgb, a, w, dash=None, phase=0.0):
        return self.g.stroke(rgb, a, w, dash, phase)

    def mesh(self, m, col, a=1.0, ycut=None, glow=0.0):
        cam = self.cam
        front, back, hatch = skia.Path(), skia.Path(), skia.Path()
        corners = []

        def seg(path, p0, p1):
            c = _clip(p0, p1, ycut)
            if c:
                x0, y0 = self.P(c[0])
                x1, y1 = self.P(c[1])
                path.moveTo(x0, y0)
                path.lineTo(x1, y1)

        for pts, n, deco in m.faces:
            ctr = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts), sum(p[2] for p in pts) / len(pts))
            is_front = _dot(n, _sub(ctr, cam.pos)) < 0
            path = front if is_front else back
            for i in range(len(pts)):
                seg(path, pts[i], pts[(i + 1) % len(pts)])
            if not is_front:
                continue
            for line in deco:
                for i in range(len(line) - 1):
                    seg(front, line[i], line[i + 1])
            if len(pts) == 4 and self.style != "neon":
                nh = 6 if self.style == "blueprint" else 4
                for j in range(1, nh):
                    u = j / nh
                    seg(hatch, _lerp(pts[0], pts[3], u), _lerp(pts[1], pts[2], u))
            if self.style == "blueprint":
                corners += pts
        for pts, ctr, closed in m.curves:
            dc = cam.p(ctr)[2]
            rng = range(len(pts)) if closed else range(len(pts) - 1)
            for i in rng:
                a0, a1 = pts[i], pts[(i + 1) % len(pts)]
                mid = _lerp(a0, a1, 0.5)
                seg(front if cam.p(mid)[2] <= dc else back, a0, a1)
        for line in m.lines:
            for i in range(len(line) - 1):
                seg(front, line[i], line[i + 1])
        bg = self.bg
        c = mix(col, (255, 255, 255), 0.35 * glow)
        if self.style != "neon":
            self.g.c.drawPath(back, self._paint(mix(bg, col, 0.55), a, 2.2, (2, 7)))
            self.g.c.drawPath(hatch, self._paint(mix(bg, col, 0.32), a, 1.5))
        wide = 13 if self.style == "neon" else (0 if self.style == "blueprint" else 9)
        if wide:
            self.g.c.drawPath(front, self._paint(mix(bg, c, 0.28 + 0.2 * glow), a, wide + 6 * glow))
        self.g.c.drawPath(front, self._paint(c, a, 4.2 if self.style == "neon" else 3.2))
        self.g.c.drawPath(front, self._paint(mix(c, (255, 255, 255), 0.65), a, 1.2))
        for p in corners[:24]:
            q = cam.p(p)
            self.g.poly([(q[0] - 7, q[1]), (q[0] + 7, q[1])], c, a, 1.5)
            self.g.poly([(q[0], q[1] - 7), (q[0], q[1] + 7)], c, a, 1.5)
        for p, on in m.leds:
            if (ycut is None or p[1] <= ycut) and on:
                q = cam.p(p)
                self.g.circle(q[0], q[1], max(2.5, 0.06 * q[3]), mix(col, (255, 255, 255), 0.6), a)

    def obj(self, nd, kind, x, z, tl, t, y0=0.0, s=1.0, glow=0.0, platform=True):
        """Materialise an object out of a scan ring, on the cue word that introduces it."""
        p = clamp((tl - nd["t"]) / 0.9)
        if p <= 0:
            return 0.0, 0.0
        col = nd["acc"]
        H = HEIGHT[kind] * s
        e = emph_amount(nd, tl)
        if platform:
            self.platform(x, z, FOOT[kind] * s, col, clamp(p * 3), t, y0)
        ycut = y0 + (H + 0.05) * e_io(p) if p < 1 else None
        a = 1.0 if p >= 1 else 0.7 + 0.3 * abs(math.sin(tl * 37))
        m = build(kind, x, z, y0, s, t, self.sides, self.rot)
        self.mesh(m, col, a, ycut, max(glow, e))
        if ycut is not None:                    # the scanning ring that "prints" the hologram
            r = FOOT[kind] * s * 1.35
            pts = [self.cam.p((x + r * math.cos(2 * math.pi * i / 32), ycut, z + r * math.sin(2 * math.pi * i / 32))) for i in range(33)]
            self.g.poly([(q[0], q[1]) for q in pts], mix(col, (255, 255, 255), 0.7), 1, 3)
        return p, H

    def platform(self, x, z, r, col, a, t, y0=0.0):
        g, cam = self.g, self.cam
        for rr, dash, w in ((r * 1.3, None, 2.0), (r * 1.7, (10, 8), 2.5)):
            path = skia.Path()
            for i in range(41):
                q = cam.p((x + rr * math.cos(2 * math.pi * i / 40), y0, z + rr * math.sin(2 * math.pi * i / 40)))
                (path.moveTo if i == 0 else path.lineTo)(q[0] * self.k, q[1] * self.k)
            g.c.drawPath(path, self._paint(mix(self.bg, col, 0.6), a, w, dash, -t * 40 if dash else 0))
        for i in range(4):
            ang = t * 0.8 + i * math.pi / 2
            q0 = cam.p((x + r * 1.75 * math.cos(ang), y0, z + r * 1.75 * math.sin(ang)))
            q1 = cam.p((x + r * 2.0 * math.cos(ang), y0, z + r * 2.0 * math.sin(ang)))
            g.poly([(q0[0], q0[1]), (q1[0], q1[1])], col, a, 3)

    def arc(self, p0, p1, lift, n=22):
        return [(_lerp(p0, p1, i / n)[0], _lerp(p0, p1, i / n)[1] + lift * 4 * (i / n) * (1 - i / n), _lerp(p0, p1, i / n)[2])
                for i in range(n + 1)]

    def stream(self, p0, p1, lift, prog, t, col, count=2, speed=0.45, phase=0.0, label=None, reverse=False):
        """Live flow: a dotted motion connector that draws itself on, then packets stream along it forever."""
        if prog <= 0:
            return []
        pts = self.arc(p0, p1, lift)
        m = max(2, int(len(pts) * prog))
        path = skia.Path()
        for i, p in enumerate(pts[:m]):
            x, y = self.P(p)
            (path.moveTo if i == 0 else path.lineTo)(x, y)
        self.g.c.drawPath(path, self._paint(mix(self.bg, col, 0.3), 1, 8))
        self.g.c.drawPath(path, self._paint(col, 1, 3, (3, 9), -t * 60 * (-1 if reverse else 1)))
        us = []
        if prog >= 1:
            for c in range(count):
                u = (t * speed + phase + c / count) % 1.0
                if reverse:
                    u = 1 - u
                us.append(u)
                for j, (du, rr) in enumerate(((0.0, 1.0), (0.035, 0.7), (0.07, 0.45))):
                    uu = clamp(u - du if not reverse else u + du)
                    q = self.cam.p(self._at(pts, uu))
                    rad = max(4.0, 0.16 * q[3]) * rr
                    self.g.circle(q[0], q[1], rad, mix(col, (255, 255, 255), 0.55 if j == 0 else 0.2), 1.0 if j == 0 else 0.6)
                    if j == 0:
                        self.g.ring(q[0], q[1], rad * 1.9, col, 0.7, 2)
                if label and c == 0:
                    q = self.cam.p(self._at(pts, u))
                    self.tag(q[0], q[1] - 40, label, col, 0.95, 24)
        return us

    @staticmethod
    def _at(pts, u):
        x = u * (len(pts) - 1)
        i = min(int(x), len(pts) - 2)
        return _lerp(pts[i], pts[i + 1], x - i)

    def dotted(self, pts, col, a=1.0, w=2.5, phase=0.0):
        path = skia.Path()
        for i, p in enumerate(pts):
            x, y = self.P(p)
            (path.moveTo if i == 0 else path.lineTo)(x, y)
        self.g.c.drawPath(path, self._paint(col, a, w, (2, 8), phase))

    def solid(self, pts, col, a=1.0, w=3.0, glow=True):
        path = skia.Path()
        for i, p in enumerate(pts):
            x, y = self.P(p)
            (path.moveTo if i == 0 else path.lineTo)(x, y)
        if glow:
            self.g.c.drawPath(path, self._paint(mix(self.bg, col, 0.3), a, w + 7))
        self.g.c.drawPath(path, self._paint(col, a, w))

    def label(self, p3, text, acc, a=1.0, icon=None, size=30, value=None, lead=True):
        if text and a > 0.02:
            self.labels.append((p3, str(text), acc, a, icon, size, value, lead))

    def tag(self, x, y, text, acc, a, size, icon=None, value=None):
        """HUD callout chip: dark glass plate, accent frame + corner brackets, 3D text, optional icon."""
        g = self.g
        font = g.fonts[0]
        tw = g.width(text, font, size)
        iw = size + 22 if icon else 0
        vw = g.width(value, font, size) + 22 if value else 0
        w, h = tw + iw + vw + 40, size + 30
        x0 = max(PANEL[0] + 12, min(PANEL[0] + PANEL[2] - 12 - w, x - w / 2))
        y0 = y - h / 2
        plate = mix(self.bg, acc, 0.16)
        g.card(x0, y0, w, h, plate, a, acc, depth=8)
        g.c.drawPath(g.shape_path(x0, y0, w, h), g.stroke(mix(self.bg, acc, 0.8), a, 2))
        L = 14
        for cx, cy, sx, sy in ((x0, y0, 1, 1), (x0 + w, y0, -1, 1), (x0, y0 + h, 1, -1), (x0 + w, y0 + h, -1, -1)):
            g.poly([(cx, cy + sy * L), (cx, cy), (cx + sx * L, cy)], acc, a, 3)
        tx = x0 + 20
        if icon:
            g.icon(icon, tx + size / 2, y0 + h / 2, size * 1.05, acc, a)
            tx += iw
        g.text(text, tx, y + size * 0.36, size, HOLO_TEXT, font, a=a, depth=2, ex=acc)
        if value:
            g.text(value, tx + tw + 22, y + size * 0.36, size, acc, font, a=a, depth=2, ex=mix(acc, (0, 0, 0), 0.5))

    def draw_labels(self):
        items = [(self.cam.p(l[0]), l) for l in self.labels]
        for q, (p3, text, acc, a, icon, size, value, lead) in sorted(items, key=lambda it: -it[0][2]):
            y = q[1] - 80
            if lead:
                self.g.poly([(q[0], q[1]), (q[0], y + 22)], mix(self.bg, acc, 0.8), a, 2, dash=(3, 6))
                self.g.circle(q[0], q[1], 5, acc, a)
            self.tag(q[0], y, text, acc, a, round(size * 1.25), icon, value)


def holo_bg(pal):
    return mix(pal["text"], (0, 0, 0), 0.55) if pal["light"] else mix(pal["bg"], (0, 0, 0), 0.35)


def emph_amount(nd, tl):
    if nd.get("emph") is not None and tl >= nd["emph"]:
        return clamp((tl - nd["emph"]) / 0.3) * (0.5 + 0.5 * math.sin((tl - nd["emph"]) * 7))
    return 0.0


def counting(value, prog):
    """Live-updating number: counts up to the value inside the string."""
    s = str(value or "")
    num = "".join(ch for ch in s if ch.isdigit() or ch == ".").strip(".")
    if not num or num.count(".") > 1:
        return s
    cur = float(num) * e_out(prog)
    fmt = f"{cur:.1f}" if "." in num else (f"{int(round(cur)):,}" if "," in s else f"{int(round(cur))}")
    return s.replace(num, fmt, 1) if num in s else fmt


# ---------------------------------------------------------------- viewport, floor, camera
def panel_image(v):
    img = getattr(v, "_holo_panel", None)
    if img is not None:
        return img
    g, k, pal = v.g, v.k, v.pal
    bg, acc = holo_bg(pal), pal["accents"][0]
    x, y, w, h = PANEL
    surf = skia.Surface(int(w * k), int(h * k))
    c = surf.getCanvas()
    c.clear(skia.ColorTRANSPARENT)
    rr = skia.RRect.MakeRectXY(skia.Rect.MakeWH(w * k, h * k), 34 * k, 34 * k)
    c.drawRRect(rr, skia.Paint(AntiAlias=True, Shader=skia.GradientShader.MakeRadial(
        skia.Point(w * k / 2, h * k * 0.55), w * k * 0.75, [g.col(mix(bg, acc, 0.16)), g.col(bg)])))
    c.save()
    c.clipRRect(rr, True)
    line = skia.Paint(Color=g.col(mix(bg, (0, 0, 0), 0.3)), StrokeWidth=1.2 * k, Style=skia.Paint.kStroke_Style)
    for yy in range(0, int(h), 6):
        c.drawLine(0, yy * k, w * k, yy * k, line)
    c.restore()
    c.drawRRect(rr, skia.Paint(AntiAlias=True, Color=g.col(mix(bg, acc, 0.55)), Style=skia.Paint.kStroke_Style, StrokeWidth=3 * k))
    br = skia.Paint(AntiAlias=True, Color=g.col(acc), Style=skia.Paint.kStroke_Style, StrokeWidth=6 * k, StrokeCap=skia.Paint.kRound_Cap)
    L, m = 60, 18
    for cx, cy, sx, sy in ((m, m, 1, 1), (w - m, m, -1, 1), (m, h - m, 1, -1), (w - m, h - m, -1, -1)):
        pth = skia.Path()
        pth.moveTo(cx * k, (cy + sy * L) * k)
        pth.lineTo(cx * k, cy * k)
        pth.lineTo((cx + sx * L) * k, cy * k)
        c.drawPath(pth, br)
    v._holo_panel = surf.makeImageSnapshot().makeRasterImage()
    return v._holo_panel


def floor(h, ext, t):
    g, cam, bg = h.g, h.cam, h.bg
    acc = h.pal["accents"][0]
    colr = mix(bg, acc, 0.38)
    E = ext + 1.6
    kind = h.dna["floor"]
    if kind in ("rings", "radar"):
        r = 1.4
        while r <= E:
            h.dotted([(r * math.cos(a), 0, r * math.sin(a)) for a in [i * math.pi / 30 for i in range(61)]], colr, 1, 2.5,
                     -t * 20 if kind == "rings" else 0)
            r += 1.4
        if kind == "radar":
            ang = t * 1.4
            h.solid([(0, 0, 0), (E * math.cos(ang), 0, E * math.sin(ang))], mix(bg, acc, 0.75), 1, 3)
            for i in range(1, 6):
                a2 = ang - i * 0.07
                h.solid([(0, 0, 0), (E * math.cos(a2), 0, E * math.sin(a2))], mix(bg, acc, 0.75 - i * 0.11), 1, 2, glow=False)
        else:
            for i in range(12):
                a = i * math.pi / 6
                h.dotted([(1.4 * math.cos(a), 0, 1.4 * math.sin(a)), (E * math.cos(a), 0, E * math.sin(a))], colr, 1, 2)
    elif kind == "grid":
        st = 1.2
        n = int(E / st)
        for i in range(-n, n + 1):
            c = i * st
            hz = math.sqrt(max(0.0, E * E - c * c))
            h.dotted([(c, 0, -hz), (c, 0, hz)], colr, 1, 2.2)
            h.dotted([(-hz, 0, c), (hz, 0, c)], colr, 1, 2.2)
    else:  # hex lattice
        st = 1.1
        n = int(E / st) + 1
        for i in range(-n, n + 1):
            for j in range(-n, n + 1):
                x = (i + 0.5 * (j % 2)) * st * 1.15
                z = j * st
                if x * x + z * z <= E * E:
                    q = cam.p((x, 0, z))
                    pts = []
                    for s in range(7):
                        a = math.pi / 6 + s * math.pi / 3
                        qq = cam.p((x + 0.5 * math.cos(a), 0, z + 0.5 * math.sin(a)))
                        pts.append((qq[0], qq[1]))
                    g.poly(pts, colr, 1, 1.6)
    pts = [(E * math.cos(a), 0, E * math.sin(a)) for a in [i * math.pi / 40 for i in range(81)]]
    h.solid(pts, mix(bg, acc, 0.65), 1, 3)


SYM = ("holo_hub", "holo_orbit", "holo_pipeline", "holo_cluster")
EXT = {"holo_flow": lambda n: n * min(3.4, 12.5 / n) / 2 + 1.2, "holo_hub": lambda n: 5.6, "holo_orbit": lambda n: 5.4,
       "holo_layers": lambda n: 4.4, "holo_cluster": lambda n: 5.4, "holo_pipeline": lambda n: 5.6,
       "holo_tree": lambda n: 5.2, "holo_chart": lambda n: n * min(2.2, 10.0 / n) / 2 + 1.4, "holo_compare": lambda n: 4.6,
       "holo_timeline": lambda n: 5.6}
TARGET = {"holo_layers": (0, 2.2, 0), "holo_tree": (0, 1.7, 1.2), "holo_chart": (0, 1.6, 0), "holo_orbit": (0, 1.3, 0),
          "holo_compare": (0, 1.0, 0), "holo_flow": (0, 0.8, 0), "holo_hub": (0, 0.5, 0), "holo_cluster": (0, 0.6, 0),
          "holo_pipeline": (0, 0.4, 0), "holo_timeline": (0, 0.8, 0)}


def make_cam(v, s, tl, t, kind, ext):
    m = v.dna["cam"]
    idx = v.scenes.index(s)
    base = 0.5 if idx % 2 else -0.5
    D = max(12.5, ext * 2.6)
    pitch, dist, yaw, roll = 0.5, D, base, 0.0
    dur = max(3.0, s["dur"])
    if m == "orbit":
        yaw = base + (t * 0.22 if kind in SYM else 0.4 * math.sin(t * 0.33))
    elif m == "sway":
        yaw = base + 0.34 * math.sin(t * 0.6)
        pitch = 0.46 + 0.06 * math.sin(t * 0.45)
    elif m == "crane":
        pitch = 0.26 + 0.42 * e_io(tl / dur)
        yaw = base + 0.2 * math.sin(tl * 0.4)
    elif m == "dolly":
        dist = D * (1.28 - 0.28 * e_io(tl / dur))
        yaw = base + 0.2 * math.sin(t * 0.4)
    else:  # dutch
        yaw = base + 0.3 * math.sin(t * 0.5)
        roll = 0.06 * math.sin(t * 0.7)
    sw = 1 - e_out(tl / 1.6)           # VR fly-in at the start of every holo scene
    yaw += 1.2 * sw * (1 if base > 0 else -1)
    dist += 11 * sw
    pitch += 0.35 * sw
    return Cam(yaw, pitch, dist, F * 1.6, 540, PANEL[1] + PANEL[3] * 0.53, TARGET.get(kind, (0, 0.6, 0))), roll


# ---------------------------------------------------------------- the ten formats
def appear(nd, tl, d=0.6):
    return clamp((tl - nd["t"]) / d)


def f_flow(h, nodes, tl, t):
    n = len(nodes)
    sp = min(3.4, 12.5 / n)
    pos = [((j - (n - 1) / 2) * sp, 0.9 * (-1) ** j) for j in range(n)]
    tops = {}
    glow = [0.0] * n
    for j in range(n - 1):
        a, b = nodes[j], nodes[j + 1]
        if tl > b["t"] + 0.3:
            ka, kb = kind_for(a["item"], h.sides), kind_for(b["item"], h.sides)
            us = h.stream((pos[j][0], HEIGHT[ka] * 0.6, pos[j][1]), (pos[j + 1][0], HEIGHT[kb] * 0.6, pos[j + 1][1]), 1.3,
                          e_io((tl - b["t"] - 0.3) / 0.6), t, a["acc"], 2, 0.42, j * 0.17, a["item"].get("packet"))
            if any(u > 0.88 for u in us):
                glow[j + 1] = 0.6
    for j, nd in enumerate(nodes):
        kd = kind_for(nd["item"], h.sides)
        p, H = h.obj(nd, kd, pos[j][0], pos[j][1], tl, t, glow=glow[j])
        tops[j] = H
        if p > 0:
            h.label((pos[j][0], H + 0.3, pos[j][1]), nd["item"].get("label"), nd["acc"], clamp(p * 2), nd["item"].get("icon"), 27)


def f_hub(h, nodes, tl, t):
    c0 = nodes[0]
    k0 = kind_for(c0["item"], h.sides)
    m = len(nodes) - 1
    R = 4.4
    for j, nd in enumerate(nodes[1:], start=1):
        ang = 2 * math.pi * (j - 1) / m + 0.35
        x, z = R * math.cos(ang), R * math.sin(ang)
        kd = kind_for(nd["item"], h.sides)
        start = max(c0["t"], nd["t"]) + 0.3
        prog = e_io((tl - start) / 0.6)
        h.stream((0, 1.0, 0), (x, HEIGHT[kd] * 0.6 * 0.85, z), 1.0, prog, t, h.pal["accents"][1], 1, 0.5, j * 0.23)
        h.stream((0, 1.2, 0), (x, HEIGHT[kd] * 0.85, z), 1.9, prog, t, h.pal["accents"][2], 1, 0.38, j * 0.41, reverse=True)
        p, H = h.obj(nd, kd, x, z, tl, t, s=0.85)
        if p > 0:
            h.label((x, H + 0.25, z), nd["item"].get("label"), nd["acc"], clamp(p * 2), nd["item"].get("icon"), 26)
    p, H = h.obj(c0, k0, 0, 0, tl, t, s=1.35)
    if p > 0:
        h.label((0, H + 0.35, 0), c0["item"].get("label"), c0["acc"], clamp(p * 2), c0["item"].get("icon"), 32)


def f_orbit(h, nodes, tl, t):
    c0 = nodes[0]
    core = (0, 1.4, 0)
    p0 = appear(c0, tl, 0.9)
    radii = (2.8, 3.8)
    tilts = (0.22, -0.16)

    def ring_pt(ri, th):
        return (radii[ri] * math.cos(th), core[1] + radii[ri] * tilts[ri] * math.sin(th), radii[ri] * math.sin(th))

    if p0 > 0:
        for ri in range(2):
            rp = e_io((tl - c0["t"] - 0.2 - ri * 0.2) / 1.0)
            if rp > 0:
                pts = [ring_pt(ri, 2 * math.pi * i / 72) for i in range(int(72 * rp) + 1)]
                h.dotted(pts, mix(h.bg, c0["acc"], 0.85), 1, 3, -t * 30)
    m = max(1, len(nodes) - 1)
    for j, nd in enumerate(nodes[1:], start=1):
        p = appear(nd, tl, 0.6)
        if p <= 0:
            continue
        ri = (j - 1) % 2
        th = 2 * math.pi * (j - 1) / m + t * (0.42 if ri == 0 else -0.28)
        x, y, z = ring_pt(ri, th)
        h.dotted([core, (x, y, z)], mix(h.bg, nd["acc"], 0.5), p, 1.8)
        kd = kind_for(nd["item"], h.sides)
        pp, H = h.obj(nd, kd, x, z, tl, t, y0=y - 0.35, s=0.6, platform=False)
        h.label((x, y - 0.35 + H + 0.2, z), nd["item"].get("label"), nd["acc"], clamp(p * 2), nd["item"].get("icon"), 25)
    if p0 > 0:
        h.obj(c0, "globe", 0, 0, tl, t, y0=0.3, s=1.55)
        h.label((0, 0.3 + 1.5 * 1.55 + 0.2, 0), c0["item"].get("label"), c0["acc"], clamp(p0 * 2), c0["item"].get("icon"), 32)


def f_layers(h, nodes, tl, t):
    n = len(nodes)
    gap, W, D = 1.45, 2.9, 2.0
    top = (n - 1) * gap
    shown = [j for j, nd in enumerate(nodes) if tl >= nd["t"]]
    if len(shown) >= 2:
        for cx, cz in ((-W, -D), (W, -D), (W, D), (-W, D)):
            h.dotted([(cx, 0, cz), (cx, shown[-1] * gap, cz)], mix(h.bg, h.pal["accents"][0], 0.6), 1, 2)
    ys = (0.5 + 0.5 * math.sin(t * 1.1)) * top
    for j, nd in enumerate(nodes):
        p = appear(nd, tl, 0.7)
        if p <= 0:
            continue
        y = j * gap + 4 * (1 - e_out(p))
        near = clamp(1 - abs(y - ys) / 0.5) if len(shown) == n else 0.0
        m = Mesh()
        grid = [[(-W + W * 2 * i / 6, y, -D), (-W + W * 2 * i / 6, y, D)] for i in range(1, 6)]
        grid += [[(-W, y, -D + D * 2 * i / 4), (W, y, -D + D * 2 * i / 4)] for i in range(1, 4)]
        m.faces.append(([(-W, y, -D), (W, y, -D), (W, y, D), (-W, y, D)], (0, 1, 0), grid))
        a = clamp(p * 2)
        h.mesh(m, nd["acc"], a, None, max(near, emph_amount(nd, tl)))
        kd = kind_for(nd["item"], h.sides)
        if nd["item"].get("icon"):
            h.obj(nd, kd, 0, 0, tl, t, y0=y, s=0.55, platform=False)
        h.label((W, y, -D), nd["item"].get("label"), nd["acc"], a, nd["item"].get("icon"), 27)
    if len(shown) == n:
        m = Mesh()
        m.faces.append(([(-W - 0.3, ys, -D - 0.3), (W + 0.3, ys, -D - 0.3), (W + 0.3, ys, D + 0.3), (-W - 0.3, ys, D + 0.3)], (0, 1, 0), []))
        h.mesh(m, (255, 255, 255), 0.8)


def f_cluster(h, nodes, tl, t):
    src = nodes[0]
    ks = kind_for(src["item"], h.sides)
    workers = nodes[1:]
    m = len(workers)
    sp = min(2.8, 10.5 / max(1, m))
    wpos = [((j - (m - 1) / 2) * sp, 2.0 - 0.5 * abs(j - (m - 1) / 2)) for j in range(m)]
    spos = (0, -3.0)
    live = [j for j, nd in enumerate(workers) if tl > nd["t"] + 0.4] if tl > src["t"] else []
    for j in live:
        h.dotted([(spos[0], 1.0, spos[1]), (wpos[j][0], 0.9, wpos[j][1])], mix(h.bg, workers[j]["acc"], 0.45), 1, 2)
    rate = 1.8
    load = [0.0] * m
    if live:
        base = int(t * rate)
        for kk in range(4):
            idx = base - kk
            u = (t * rate - idx) / 1.6
            if 0 <= u <= 1:
                j = live[idx % len(live)]
                pts = h.arc((spos[0], 1.0, spos[1]), (wpos[j][0], 1.0, wpos[j][1]), 1.1)
                q = h.cam.p(h._at(pts, u))
                rad = max(4.0, 0.16 * q[3])
                h.g.circle(q[0], q[1], rad, mix(workers[j]["acc"], (255, 255, 255), 0.5))
                h.g.ring(q[0], q[1], rad * 1.9, workers[j]["acc"], 0.7, 2)
                if u > 0.85:
                    load[j] = 0.6
    for j, nd in enumerate(workers):
        kd = kind_for(nd["item"], h.sides)
        p, H = h.obj(nd, kd, wpos[j][0], wpos[j][1], tl, t, s=0.85, glow=load[j])
        if p > 0:
            lv = 0.4 + 0.5 * abs(math.sin(t * 1.3 + j * 1.7))
            bx = wpos[j][0] + 0.95
            mm = Mesh()                     # live load bar beside each worker
            _prism(mm, lambda q: q, bx, wpos[j][1], 0, 0.16, 1.6 * lv * p, 4, math.pi / 4)
            h.mesh(mm, nd["acc"], 1)
            h.label((wpos[j][0], H + 0.25, wpos[j][1]), nd["item"].get("label"), nd["acc"], clamp(p * 2), nd["item"].get("icon"), 25,
                    f"{int(lv * 100)}%")
    p, H = h.obj(src, ks, spos[0], spos[1], tl, t, s=1.05)
    if p > 0:
        h.label((spos[0], H + 0.3, spos[1]), src["item"].get("label"), src["acc"], clamp(p * 2), src["item"].get("icon"), 30)


def f_pipeline(h, nodes, tl, t):
    n = len(nodes)
    A, B = 4.6, 2.7
    loop = lambda th: (A * math.cos(th), 0.0, B * math.sin(th))
    shown = sum(1 for nd in nodes if tl >= nd["t"])
    if shown:
        prog = e_io((tl - nodes[0]["t"]) / 1.4)
        h.dotted([(loop(-math.pi / 2 + 2 * math.pi * i / 90)[0], 0.02, loop(-math.pi / 2 + 2 * math.pi * i / 90)[2])
                  for i in range(int(90 * prog) + 1)], mix(h.bg, h.pal["accents"][0], 0.85), 1, 3.5, -t * 40)
    ths = [-math.pi / 2 + 2 * math.pi * j / n for j in range(n)]
    cube_col = h.pal["accents"][0]
    if shown >= 2:
        thc = (t * 0.55) % (2 * math.pi) - math.pi / 2
        passed = [j for j in range(n) if ths[j] <= thc + 1e-6 and tl >= nodes[j]["t"]]
        if passed:
            cube_col = nodes[passed[-1]]["acc"]
        x, _, z = loop(thc)
        mm = Mesh()
        _prism(mm, lambda q: q, x, z, 0.35 + 0.15 * math.sin(t * 4), 0.42, 0.6, 4, t * 2)
        h.mesh(mm, cube_col, 1, None, 0.3)
    for j, nd in enumerate(nodes):
        p = appear(nd, tl, 0.7)
        if p <= 0:
            continue
        x, _, z = loop(ths[j])
        ang = ths[j]
        tx, tz = -math.sin(ang), math.cos(ang)       # tangent: the gate spans across the path
        nx, nz = math.cos(ang), math.sin(ang)
        w = 0.9
        Hh = 1.9 * e_out(p)
        m = Mesh()
        for sgn in (-1, 1):
            px, pz = x + nx * w * sgn, z + nz * w * sgn
            _prism(m, lambda q: q, px, pz, 0, 0.13, Hh, 4, ang)
        m.lines.append([(x - nx * w, Hh, z - nz * w), (x + nx * w, Hh, z + nz * w)])
        m.lines.append([(x - nx * w, Hh - 0.25, z - nz * w), (x + nx * w, Hh - 0.25, z + nz * w)])
        h.mesh(m, nd["acc"], clamp(p * 2), None, emph_amount(nd, tl))
        h.label((x, Hh + 0.2, z), nd["item"].get("label"), nd["acc"], clamp(p * 2), nd["item"].get("icon"), 25)


def f_tree(h, nodes, tl, t):
    n = len(nodes)
    root = nodes[0]
    kids = list(range(1, n))
    lvl1 = [i for i in kids if int(nodes[i]["item"].get("parent", 0) or 0) == 0][:4] or kids[:4]
    lvl2 = [i for i in kids if i not in lvl1]
    pos = {0: (0.0, 3.3, 0.0)}
    for j, i in enumerate(lvl1):
        pos[i] = ((j - (len(lvl1) - 1) / 2) * 3.0, 0.0, 0.0)
    for j, i in enumerate(lvl2):
        par = int(nodes[i]["item"].get("parent", 0) or 0)
        par = par if par in lvl1 else lvl1[j % len(lvl1)]
        sib = [q for q in lvl2 if (int(nodes[q]["item"].get("parent", 0) or 0) == par) or q == i]
        off = (sib.index(i) - (len(sib) - 1) / 2) * 1.8 if i in sib else 0
        pos[i] = (pos[par][0] + off, 0.0, 3.0)
        nodes[i]["_par"] = par
    for i in kids:
        par = nodes[i].get("_par", 0)
        a, b = nodes[par], nodes[i]
        start = max(a["t"], b["t"]) + 0.3
        pa, pb = pos[par], pos[i]
        ka, kb = kind_for(a["item"], h.sides), kind_for(b["item"], h.sides)
        h.stream((pa[0], pa[1] + (0 if par == 0 else HEIGHT[ka]), pa[2]), (pb[0], HEIGHT[kb] * 0.9, pb[2]), 0.6,
                 e_io((tl - start) / 0.6), t, a["acc"], 1, 0.45, i * 0.21)
    for i in kids:
        nd = nodes[i]
        x, y, z = pos[i]
        kd = kind_for(nd["item"], h.sides)
        p, H = h.obj(nd, kd, x, z, tl, t, s=0.8 if i in lvl2 else 0.95)
        if p > 0:
            h.label((x, H + 0.25, z), nd["item"].get("label"), nd["acc"], clamp(p * 2), nd["item"].get("icon"), 25)
    p, H = h.obj(root, kind_for(root["item"], h.sides), 0, 0, tl, t, y0=3.3, s=1.1, platform=False)
    if p > 0:
        h.dotted([(0, 3.3, 0), (0, 0, 0)], mix(h.bg, root["acc"], 0.7), p, 2.5, -t * 30)
        h.platform(0, 0, 0.8, root["acc"], p, t, 3.3)
        h.label((0, 3.3 + H + 0.3, 0), root["item"].get("label"), root["acc"], clamp(p * 2), root["item"].get("icon"), 30)


def f_chart(h, nodes, tl, t):
    n = len(nodes)
    sp = min(2.2, 10.0 / n)
    vals = [_num(nd["item"].get("value")) for nd in nodes]
    vmax = max(vals + [1e-9])
    xs = [(j - (n - 1) / 2) * sp for j in range(n)]
    Wd = xs[-1] + sp * 0.8
    wall = mix(h.bg, h.pal["accents"][0], 0.45)
    first = nodes[0]["t"]
    if tl > first:
        a = clamp((tl - first) / 0.6)
        for i in range(1, 6):
            h.dotted([(-Wd, i * 0.9, 1.2), (Wd, i * 0.9, 1.2)], wall, a, 2)
        h.solid([(-Wd, 0, 1.2), (-Wd, 5 * 0.9, 1.2)], wall, a, 2.5, False)
    tops = []
    for j, nd in enumerate(nodes):
        p = appear(nd, tl, 0.5)
        if p <= 0:
            continue
        hu = e_out(clamp((tl - nd["t"]) / 1.2))
        Hh = (0.35 + 4.1 * clamp(vals[j] / vmax)) * hu
        m = Mesh()
        _box(m, lambda q: q, xs[j], 0, 0, sp * 0.5, max(0.02, Hh), sp * 0.5)
        h.platform(xs[j], 0, sp * 0.3, nd["acc"], p, t)
        h.mesh(m, nd["acc"], 1, None, emph_amount(nd, tl))
        tops.append((xs[j], Hh + 0.02, 0))
        h.label((xs[j], Hh + 0.2, 0), counting(nd["item"].get("value"), clamp((tl - nd["t"]) / 1.2)), nd["acc"], clamp(p * 2), None, 28)
        h.label((xs[j], -0.75, -0.6), nd["item"].get("label"), nd["acc"], clamp(p * 2), nd["item"].get("icon"), 23, lead=False)
    if len(tops) >= 2:
        h.solid(tops, h.pal["accents"][1], 1, 4)
        for p3 in tops:
            q = h.cam.p(p3)
            h.g.circle(q[0], q[1], 9, mix(h.pal["accents"][1], (255, 255, 255), 0.5))


def f_compare(h, nodes, tl, t):
    xs = (-2.7, 2.7)
    for j, nd in enumerate(nodes[:2]):
        kd = kind_for(nd["item"], h.sides)
        p, H = h.obj(nd, kd, xs[j], 0, tl, t, s=1.35)
        if p > 0:
            h.label((xs[j], H + 0.35, 0), nd["item"].get("label"), nd["acc"], clamp(p * 2), nd["item"].get("icon"), 30)
            val = nd["item"].get("value")
            if val:
                h.label((xs[j], -0.9, -1.6), counting(val, clamp((tl - nd["t"]) / 1.3)), nd["acc"], clamp(p * 2), None, 34, lead=False)
            if nd["item"].get("sub"):
                h.label((xs[j], -1.9, -1.6), nd["item"]["sub"], nd["acc"], clamp(p * 2), None, 22, lead=False)
    if len(nodes) >= 2 and tl > nodes[1]["t"]:
        a = clamp((tl - nodes[1]["t"]) / 0.5)
        c = (0, 1.3, 0)
        pts = [(c[0] + 0.75 * math.cos(u) * math.cos(t), c[1] + 0.75 * math.sin(u), c[2] + 0.75 * math.cos(u) * math.sin(t))
               for u in [2 * math.pi * i / 40 for i in range(41)]]
        h.solid(pts, h.pal["accents"][3 % len(h.pal["accents"])], a, 3)
        q = h.cam.p(c)
        h.g.text("VS", q[0], q[1] + 16, 44, HOLO_TEXT, h.g.fonts[0], "center", a, depth=4, ex=h.pal["accents"][0])
        vals = [_num(nd["item"].get("value")) for nd in nodes[:2]]
        vm = max(vals + [1e-9])
        for j in range(2):
            ln = 2.4 * vals[j] / vm * e_out(clamp((tl - nodes[1]["t"]) / 1.2))
            sgn = -1 if j == 0 else 1
            h.solid([(sgn * 0.4, 0.02, -2.6), (sgn * (0.4 + ln), 0.02, -2.6)], nodes[j]["acc"], a, 8)


def f_timeline(h, nodes, tl, t):
    n = len(nodes)
    pts = [(-4.6 + 9.2 * j / max(1, n - 1), 0.0, -1.8 + 3.6 * j / max(1, n - 1)) for j in range(n)]
    shown = [j for j, nd in enumerate(nodes) if tl >= nd["t"]]
    if shown:
        last = shown[-1]
        path = []
        for j in range(last):
            seg_p = e_io((tl - nodes[j + 1]["t"]) / 0.6)
            path += [_lerp(pts[j], pts[j + 1], i / 10) for i in range(int(10 * seg_p) + 1)]
        if len(path) >= 2:
            h.solid(path, h.pal["accents"][0], 1, 4)
        far = _lerp(pts[-1], (pts[-1][0] + 2, 0, pts[-1][2] + 0.8), 1)
        h.dotted([pts[last], far] if last == n - 1 else [pts[last], pts[-1]], mix(h.bg, h.pal["accents"][0], 0.6), 1, 3, -t * 30)
        if len(path) >= 2:
            u = (t * 0.35) % 1.0
            q = h.cam.p(h._at(path, u))
            h.g.circle(q[0], q[1], 11, mix(h.pal["accents"][1], (255, 255, 255), 0.5))
            h.g.ring(q[0], q[1], 22, h.pal["accents"][1], 0.7, 2)
    for j, nd in enumerate(nodes):
        p = appear(nd, tl, 0.7)
        if p <= 0:
            continue
        x, _, z = pts[j]
        Hh = (0.9 + 0.35 * j) * e_out(p)
        m = Mesh()
        _prism(m, lambda q: q, x, z, 0, 0.32, Hh, h.sides, h.rot)
        h.platform(x, z, 0.4, nd["acc"], p, t)
        h.mesh(m, nd["acc"], 1, None, emph_amount(nd, tl))
        h.label((x, Hh + 0.2, z), nd["item"].get("label"), nd["acc"], clamp(p * 2), nd["item"].get("icon"), 24,
                nd["item"].get("value"))


BUILD = {"holo_flow": f_flow, "holo_hub": f_hub, "holo_orbit": f_orbit, "holo_layers": f_layers,
         "holo_cluster": f_cluster, "holo_pipeline": f_pipeline, "holo_tree": f_tree, "holo_chart": f_chart,
         "holo_compare": f_compare, "holo_timeline": f_timeline}


def draw(v, s, tl, t):
    kind = s["data"]["layout"]
    nodes = s["geo"]["nodes"]
    if not nodes:
        return
    g, k = v.g, v.k
    x0, y0, w, hh = PANEL
    g.c.drawImage(panel_image(v), x0 * k, y0 * k)
    g.c.save()
    g.c.clipRect(skia.Rect.MakeXYWH((x0 + 6) * k, (y0 + 6) * k, (w - 12) * k, (hh - 12) * k))
    ext = EXT[kind](len(nodes))
    cam, roll = make_cam(v, s, tl, t, kind, ext)
    h = Holo(v, cam)
    acc = v.pal["accents"][0]
    rng = random.Random(v.dna["seed"] + v.scenes.index(s))
    for i in range(22):                      # rising holo particles
        px = x0 + 30 + rng.random() * (w - 60)
        sp = 20 + rng.random() * 50
        py = y0 + hh - ((t * sp + rng.random() * hh) % hh)
        g.circle(px, py, 1.5 + rng.random() * 2.5, mix(h.bg, acc, 0.35 + 0.4 * rng.random()))
    g.c.save()
    if roll:
        g.c.rotate(math.degrees(roll), cam.cx * k, cam.cy * k)
    floor(h, ext, t)
    BUILD[kind](h, nodes, tl, t)
    h.draw_labels()
    g.c.restore()
    sy = y0 + (t * 260) % hh                 # live scan bar
    g.c.drawRect(skia.Rect.MakeXYWH(x0 * k, sy * k, w * k, 2.5 * k), g.fill(mix(h.bg, acc, 0.6)))
    g.c.restore()
    blink = 1.0 if int(t * 2) % 2 == 0 else 0.35
    g.circle(x0 + 52, y0 + 52, 8, (255, 70, 80), blink)
    g.text("LIVE", x0 + 70, y0 + 61, 24, HOLO_TEXT, g.fonts[2])
    g.text(kind.replace("holo_", "SYS.").upper(), x0 + w - 40, y0 + 61, 22, mix(h.bg, acc, 0.9), g.fonts[2], "right")
    g.text(f"T+{t:05.1f}s", x0 + 40, y0 + hh - 34, 20, mix(h.bg, acc, 0.8), g.fonts[2])
    g.text(f"YAW {math.degrees(math.atan2(cam.syw, cam.cyw)):+05.0f}°", x0 + w - 40, y0 + hh - 34, 20, mix(h.bg, acc, 0.8),
           g.fonts[2], "right")
