"""
3D carousels, attractive edition (5 slides): recognizable 3D objects (phone, chip, router, lock...) rendered by the
engine as the full-bleed background, REAL data charts drawn from real numbers (bars / comparison / donut), a hook cover
with a big number and a SAVE THIS ribbon, dense info slides, and a summary that teases Part 2 (a reason to follow).

  python carousel3d.py --format versus --topic "SSD vs hard drive"     # make one locally (nothing posted)
"""
import argparse
import json
import random
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

import art_director
import carousel_lane as lane
import covers
import research
import writer

BASE = Path(__file__).resolve().parent
W, H, M = 1080, 1350, 72
OBJECTS = writer.OBJECTS
WRITE = """You write a premium, highly shareable Instagram carousel for "DataVelvet", a 3D tech-explainer brand for
everyday people. Goal: people SAVE it, SHARE it and FOLLOW for more. Topic: "{topic}". Format: {fmt_desc}
{facts}
Return ONLY JSON:
{{"title": scroll-stopping cover headline, max 44 chars (a surprising truth, a question or a promise),
  "cover_stat": {{"value": the single most striking real number that DIRECTLY supports the title's hook (max 8 chars,
                 e.g. "100x"), "label": max 34 chars}},
  "subtitle": max 70 chars, "object": the 3D object for the cover, one of {objects},
  "sections": [3 objects: {{"heading": max 28 chars,
      "points": [3 specific points, max 80 chars each - real facts, comparisons or tips],
      "chart": {{"kind": "bars" or "compare" or "donut", "title": max 40 chars, "unit": short unit or "",
                "items": [2-5 {{"label": max 14 chars, "value": a real number}}]}} - ONLY with real, well-established numbers
                from the reference facts or common knowledge; use null when there are no real numbers,
      "object": the 3D object that best represents this section, one of {objects}}}],
  "summary": [4 one-line takeaways, max 56 chars each],
  "next_topic": a related follow-up topic for "Part 2" (max 44 chars),
  "caption": 2 short lines + "Save this for later." + 6 relevant hashtags}}
For a comparison, points look like "SSD: ... | HDD: ...". For myths, each point starts with "Myth:" or "Fact:".
Accurate facts only - never invent or round up statistics. No emojis. The title must not promise more items than the
slides show (3 sections)."""


def write_content(topic, fmt):
    facts = research.gather(topic, llm=writer.llm)
    ftxt = (f"REFERENCE FACTS (from {', '.join(facts['sources'][:3])}):\n{facts['facts'][:3000]}") if facts.get("facts") else ""
    err = ""
    for _ in range(3):
        c = json.loads(writer.llm(WRITE.format(topic=topic, fmt_desc=lane.FORMATS[fmt][1], facts=ftxt, objects=", ".join(OBJECTS)) + err,
                                  label="carousel 3d"))
        secs = [s for s in (c.get("sections") or []) if isinstance(s, dict) and s.get("heading") and s.get("points")][:3]
        if len(secs) < 3:
            err = "\nGive exactly 3 sections, each with 3 points."
            continue
        c["sections"] = secs

        def lines(s):
            ch = s.get("chart") if isinstance(s.get("chart"), dict) else None
            extra = [f'Chart "{ch.get("title", "")}": ' + ", ".join(f'{i.get("label")} = {i.get("value")} {ch.get("unit", "")}'
                                                                    for i in ch.get("items", []) if isinstance(i, dict))] if ch else []
            return [*s["points"], *extra]
        cs = c.get("cover_stat") or {}
        rv = writer.review({"topic": topic, "scenes": [{"plate": "compose", "title": c["title"], "lines": [f'{cs.get("value", "")} {cs.get("label", "")}'],
                            "data": {}}] + [{"plate": "compose", "title": s["heading"], "lines": lines(s), "data": {}} for s in secs]})
        print(f"  fact-check: {rv['score']}/10, {len(rv['critical'])} real error(s)")
        if not rv["critical"] and rv["score"] >= 7:
            c["sources"] = facts["sources"]
            return c
        err = "\nA fact-checker rejected the previous version. Fix every point (charts included):\n- " + "\n- ".join(rv["critical"] + rv["minor"])
    raise RuntimeError("no carousel passed the fact-check")


def background(still, ink, edge=0.9, mid=0.18):
    """The 3D render (cropped 4:5, no captions/header): bright in the middle, darker at the top and bottom for text."""
    img = Image.open(still).convert("RGB").resize((1080, 1920)).crop((0, 200, 1080, 1550))
    g = Image.linear_gradient("L").resize((W, H))
    mask = g.point(lambda v: int(255 * min(1, mid + (edge - mid) * (abs(v - 128) / 128) ** 1.4)))
    return Image.composite(Image.new("RGB", (W, H), ink), img, mask)


def glass(img, box, ink, alpha=185, radius=34):
    """A frosted glass panel: the background blurred and tinted under the content."""
    x0, y0, x1, y1 = [int(v) for v in box]
    img.paste(img.crop((x0, y0, x1, y1)).filter(ImageFilter.GaussianBlur(20)), (x0, y0))
    over = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(over).rounded_rectangle(box, radius, fill=(*ink, alpha), outline=(255, 255, 255, 46), width=2)
    img.paste(Image.alpha_composite(img.convert("RGBA"), over).convert("RGB"))


def _num(v):
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def chart(d, box, ch, c1, c2, ink_txt, soft):
    """A real chart from real numbers: horizontal bars (or a two-way comparison) or a donut with a legend."""
    x0, y0, x1, y1 = box
    items = [(str(i.get("label", ""))[:16], _num(i.get("value"))) for i in (ch.get("items") or []) if isinstance(i, dict)]
    items = [(lab, v) for lab, v in items if v is not None and v >= 0][:5]
    if len(items) < 2:
        return False
    unit = str(ch.get("unit") or "")
    tf, tl = covers._fit(d, str(ch.get("title", "")).upper(), x1 - x0 - 60, 1, 30, "label", 22)
    d.text((x0 + 30, y0 + 26), tl[0] if tl else "", font=tf, fill=soft)
    top = y0 + 82
    fmtv = lambda v: (f"{v:,.0f}" if v >= 100 or v == int(v) else f"{v:g}") + (f" {unit}" if unit else "")
    if ch.get("kind") == "donut":
        tot = sum(v for _, v in items) or 1
        r = min(y1 - top - 30, 280) / 2
        cx, cy = x0 + 50 + r, top + 6 + r
        a, cols = -90.0, [c1, c2, (250, 204, 21), (148, 163, 184), (236, 72, 153)]
        for k, (_, v) in enumerate(items):
            sweep = 360 * v / tot
            d.pieslice([cx - r, cy - r, cx + r, cy + r], a, a + sweep, fill=cols[k % 5])
            a += sweep
        d.ellipse([cx - r * 0.56, cy - r * 0.56, cx + r * 0.56, cy + r * 0.56], fill=(22, 22, 28))
        ly = top + 6
        for k, (lab, v) in enumerate(items):
            d.rounded_rectangle([cx + r + 44, ly + 6, cx + r + 70, ly + 32], 6, fill=cols[k % 5])
            d.text((cx + r + 84, ly), f"{lab}  {round(100 * v / tot)}%", font=covers._font(30, "body"), fill=ink_txt)
            ly += 52
        return True
    vmax = max(v for _, v in items) or 1
    lw, gap = 240, 18
    bh = min(66, (y1 - top - 24) / len(items) - gap)
    for k, (lab, v) in enumerate(items):
        y = top + k * (bh + gap)
        lf, ll = covers._fit(d, lab, lw - 20, 1, 30, "label", 20)
        d.text((x0 + 30, y + bh / 2 - lf.size * 0.62), ll[0] if ll else "", font=lf, fill=ink_txt)
        bx0, bx1 = x0 + 30 + lw, x1 - 40
        d.rounded_rectangle([bx0, y, bx1, y + bh], bh / 2, fill=(58, 58, 68))
        wv = max(bh, (bx1 - bx0) * v / vmax)
        d.rounded_rectangle([bx0, y, bx0 + wv, y + bh], bh / 2, fill=c1 if k % 2 == 0 else c2)
        vf = covers._font(int(min(32, bh * 0.55)), "head")
        txt = fmtv(v)
        inside = d.textlength(txt, font=vf) + 36 < wv
        tx = bx0 + wv - d.textlength(txt, font=vf) - 18 if inside else bx0 + wv + 14
        d.text((tx, y + bh / 2 - vf.size * 0.62), txt, font=vf, fill=(15, 15, 20) if inside else ink_txt)
    return True


def design(content, fmt, genome, stills, out_dir):
    pal = covers._palette({"style": genome})
    ink, bone, ash = pal["ink"], pal["bone"], pal["ash"]
    c1 = pal["signal"]
    c2 = covers._rgb((genome.get("holo") or ["#38bdf8"])[0])
    badge, n = lane.FORMATS[fmt][0], 5
    out = []

    def footer(d, k):
        d.text((M, H - 70), "@DATAVELVET", font=covers._font(26, "label"), fill=ash)
        for j in range(n):                                    # swipe dots
            x = W - M - (n - j) * 26
            d.ellipse([x, H - 62, x + 14, H - 48], fill=c1 if j == k - 1 else (90, 90, 100))

    img = background(stills[0], ink, 0.92, 0.1)                                       # 1. hook cover
    rib = Image.new("RGBA", (620, 84), (*c1, 255))                                   # SAVE THIS corner ribbon
    rd = ImageDraw.Draw(rib)
    rf = covers._font(36, "head")
    rd.text((310 - rd.textlength("SAVE THIS", font=rf) / 2, 22), "SAVE THIS", font=rf, fill=ink)
    rib = rib.rotate(-45, expand=True, resample=Image.BICUBIC)
    img.paste(rib, (W - rib.size[0] // 2 - 130, -rib.size[1] // 2 + 130), rib)
    d = ImageDraw.Draw(img)
    bf = covers._font(32, "label")
    d.rounded_rectangle([M, 80, M + d.textlength(badge, font=bf) + 44, 138], 29, fill=c2)
    d.text((M + 22, 90), badge, font=bf, fill=ink)
    cs = content.get("cover_stat") or {}
    f, ls = covers._fit(d, content["title"].upper(), W - 2 * M, 4, 104)
    sf, sl = covers._fit(d, content.get("subtitle", ""), W - 2 * M, 2, 36, "body", 26)
    y = H - 150 - (len(ls) * f.size * 1.05 + 30 + len(sl) * sf.size * 1.25)
    if cs.get("value"):
        vf = covers._font(160, "head")
        vw = d.textlength(str(cs["value"]), font=vf)
        vy = y - 215
        d.text((M - 6, vy), str(cs["value"]), font=vf, fill=c1)
        lf, ll = covers._fit(d, cs.get("label", ""), W - 2 * M - vw - 40, 3, 34, "label", 24)
        covers._text_block(d, ll, lf, M + vw + 30, vy + 46, bone, 1.15)
    y = covers._text_block(d, ls, f, M, y, bone, 1.05)
    covers._text_block(d, sl, sf, M, y + 30, ash, 1.25)
    footer(d, 1)
    out.append(img)
    for k, s in enumerate(content["sections"], 2):                                     # 2-4. chart + facts
        st = stills[min(k - 1, len(stills) - 1)]
        img = background(st, ink, 0.88, 0.22)
        d = ImageDraw.Draw(img)
        pts = [str(p) for p in s["points"][:3]]
        fonts = [covers._fit(d, p, W - 2 * M - 120, 2, 36, "body", 26) for p in pts]
        pts_h = sum(len(pl) * pf.size * 1.28 + 26 for pf, pl in fonts) + 60
        pt_top = H - 120 - pts_h
        ch = s.get("chart") if isinstance(s.get("chart"), dict) else None
        if ch:
            cbox = [M - 16, pt_top - 386, W - M + 16, pt_top - 26]
            glass(img, cbox, ink, 200)
            d = ImageDraw.Draw(img)
            if not chart(d, cbox, ch, c1, c2, bone, ash):          # no usable numbers: drop the chart card
                img = background(st, ink, 0.88, 0.22)
                d = ImageDraw.Draw(img)
        d.text((M, 78), f"{k - 1:02d}", font=covers._font(60, "head"), fill=c1)
        hf, hl = covers._fit(d, s["heading"].upper(), W - 2 * M - 110, 2, 66)
        covers._text_block(d, hl, hf, M + 104, 84, bone, 1.04)
        glass(img, [M - 16, pt_top, W - M + 16, H - 104], ink, 185)
        d = ImageDraw.Draw(img)
        y = pt_top + 34
        for (pf, pl), p in zip(fonts, pts):
            low = p.lower()
            dot = (235, 75, 85) if low.startswith("myth") else (52, 211, 140) if low.startswith("fact") else c2
            d.rounded_rectangle([M + 26, y + 8, M + 50, y + 32], 7, fill=dot)
            y = covers._text_block(d, pl, pf, M + 76, y, bone, 1.28) + 26
        footer(d, k)
        out.append(img)
    img = background(stills[-1], ink, 0.95, 0.55).filter(ImageFilter.GaussianBlur(4))     # 5. summary + Part 2
    d = ImageDraw.Draw(img)
    d.text((M, 90), "IN SHORT", font=covers._font(38, "label"), fill=c1)
    f, ls = covers._fit(d, content["title"].upper(), W - 2 * M, 2, 62)
    y = covers._text_block(d, ls, f, M, 146, bone, 1.05) + 36
    sums = (content.get("summary") or [])[:4]
    glass(img, [M - 16, y, W - M + 16, y + 80 + len(sums) * 104], ink, 200)
    d = ImageDraw.Draw(img)
    y += 40
    for p in sums:
        d.ellipse([M + 22, y, M + 78, y + 56], fill=c1)
        d.line([(M + 36, y + 29), (M + 47, y + 41), (M + 66, y + 17)], fill=ink, width=7)
        pf, pl = covers._fit(d, str(p), W - 2 * M - 140, 2, 36, "head", 26)
        y = max(covers._text_block(d, pl, pf, M + 104, y + 6, bone, 1.12), y + 56) + 44
    nxt = str(content.get("next_topic") or "").strip()
    if nxt:
        by = H - 330
        d.rounded_rectangle([M - 16, by, W - M + 16, by + 170], 34, fill=c2)
        d.text((M + 20, by + 24), "PART 2 IS COMING", font=covers._font(30, "label"), fill=ink)
        nf, nl = covers._fit(d, nxt, W - 2 * M - 40, 2, 44, "head", 30)
        covers._text_block(d, nl, nf, M + 20, by + 70, ink, 1.1)
    d.text((M, H - 132), "Follow @datavelvet so you don't miss it", font=covers._font(32, "label"), fill=c1)
    footer(d, 5)
    out.append(img)
    paths = []
    for k, im in enumerate(out, 1):
        p = Path(out_dir) / f"slide3d_{k}.jpg"
        im.save(p, quality=93)
        paths.append(p)
    return paths


def hero(obj, k):
    """Background scene: one recognizable 3D object (big) plus an accent ring - no labels."""
    o = obj if obj in OBJECTS else ["phone", "chip", "laptop", "router", "lock"][k % 5]
    return {"layout": random.choice(["row", "radial", "diagonal"]),
            "elements": [{"type": "object", "object": o, "label": "hero", "size": 1.7},
                         {"type": random.choice(["ring", "torus", "orbit"]), "label": "accent", "size": 1.3}]}


def make(topic, fmt):
    print(f"🗂️ 3D carousel: {lane.FORMATS[fmt][0]} - {topic}")
    content = write_content(topic, fmt)
    genome = art_director.new_genome({}, 5)
    genome.update(reflect=False, mascot={"on": False})
    genome["post"]["bloom"] = max(genome["post"].get("bloom", 0.7), 0.85)        # brighter, punchier backgrounds
    work = BASE / "out" / "carousels3d" / f"{time.strftime('%Y%m%d-%H%M%S')}_{fmt}"
    work.mkdir(parents=True, exist_ok=True)
    (work / "content.json").write_text(json.dumps(content, indent=2, ensure_ascii=False), encoding="utf-8")
    pseudo = {"title": content["title"], "visual": hero(content.get("object"), 0),        # stills: cover, 3 sections, summary
              "slides": [{"heading": s["heading"], "visual": hero(s.get("object"), k)} for k, s in enumerate(content["sections"], 1)]
              + [{"heading": "summary", "visual": hero(content.get("object"), 4)}]}
    stills = lane.render_heroes(pseudo, genome, work, labels=False)
    slides = design(content, fmt, genome, stills, work)
    print(f"✅ {len(slides)} slides in {work}")
    return slides


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--format", choices=list(lane.FORMATS), default=random.choice(list(lane.FORMATS)))
    ap.add_argument("--topic", required=True)
    a = ap.parse_args()
    make(a.topic, a.format)
