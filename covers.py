"""
Designed Instagram assets for every video, in the video's own palette and the engine's Archivo type:
  - a Reel cover (1080x1920): the hook frame, darkened, with the title as a big title card (the profile grid shows it)
  - a carousel (1080x1350 slides): hook -> 3-4 key steps with frames from the video -> cheat sheet -> follow.
Carousels earn saves and get re-shown to people who swiped past them - a second free reach source.
"""
import json
import re
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

import audio_build

BASE = Path(__file__).resolve().parent
FONTS = BASE / "app" / "public" / "fonts"


def _font(size, kind="head"):
    name = {"head": "Archivo-w1125-900.ttf", "body": "Archivo-w1000-500.ttf", "label": "Archivo-w750-700.ttf"}[kind]
    return ImageFont.truetype(str(FONTS / name), size)


def _rgb(hexcol, default=(240, 240, 240)):
    try:
        h = str(hexcol).lstrip("#")
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return default


def _frame(video, t, out):
    subprocess.run([audio_build.ffmpeg(), "-v", "error", "-y", "-ss", f"{max(0.0, t):.2f}", "-i", str(video), "-frames:v", "1", str(out)],
                   check=True)
    return Image.open(out).convert("RGB")


def _wrap(draw, text, font, width):
    lines, cur = [], ""
    for w in text.split():
        t = f"{cur} {w}".strip()
        if cur and draw.textlength(t, font=font) > width:
            lines.append(cur)
            cur = w
        else:
            cur = t
    if cur:
        lines.append(cur)
    return lines


def _fit(draw, text, width, max_lines, start, kind="head", low=40):
    """Largest font size (from start down to low) at which the text fits in max_lines."""
    for size in range(start, low - 1, -4):
        f = _font(size, kind)
        lines = _wrap(draw, text, f, width)
        if len(lines) <= max_lines:
            return f, lines
    f = _font(low, kind)
    lines = _wrap(draw, text, f, width)
    return f, lines[:max_lines - 1] + [" ".join(lines[max_lines - 1:])[:38] + "..."] if len(lines) > max_lines else lines


def _text_block(draw, lines, font, x, y, fill, gap=1.12):
    for i, ln in enumerate(lines):
        draw.text((x, y + i * font.size * gap), ln, font=font, fill=fill)
    return y + len(lines) * font.size * gap


def _shade(img, ink, top=0.25, bottom=0.85):
    """Darken an image toward the ink colour, more at the bottom (keeps text readable)."""
    w, h = img.size
    a = Image.linear_gradient("L").resize((w, h)).point(lambda v: int(255 * (top + (bottom - top) * v / 255)))
    return Image.composite(Image.new("RGB", (w, h), ink), img, a)


def _band(canvas, shot, y, h, ink):
    """Paste the 3D middle of a frame (no captions or headers) at height y, fading into the background at its edges."""
    W = canvas.size[0]
    crop = shot.crop((0, 380, W, 380 + min(h, 880))).resize((W, h))
    m = Image.linear_gradient("L").resize((W, h)).point(lambda v: int(255 * min(1, min(v, 255 - v) / 70)))
    canvas.paste(_shade(crop, ink, 0.1, 0.3), (0, y), m)
    return canvas


def _palette(script):
    p = (script.get("style") or {}).get("palette") or {}
    return {"ink": _rgb(p.get("ink"), (10, 10, 14)), "bone": _rgb(p.get("bone"), (240, 236, 228)),
            "signal": _rgb(p.get("signal"), (255, 77, 18)), "ash": _rgb(p.get("ash"), (150, 150, 150))}


def clean_title(script):
    t = (script.get("youtube") or {}).get("title") or script.get("topic") or ""
    return re.sub(r"\s*#\w+", "", t).strip()


def scene_times():
    ly = json.loads((BASE / "data" / "lyrics.json").read_text(encoding="utf-8"))
    out = {}
    for ln in ly["lines"]:
        a, b = out.get(ln["scene"], (ln["start"], ln["end"]))
        out[ln["scene"]] = (min(a, ln["start"]), max(b, ln["end"]))
    return out


def reel_cover(video, script, out_path, t):
    pal = _palette(script)
    src = Path(out_path).with_suffix(".src.png")
    img = _band(Image.new("RGB", (1080, 1920), pal["ink"]), _frame(video, t, src).resize((1080, 1920)), 1060, 860, pal["ink"])
    d = ImageDraw.Draw(img)
    series = ((script.get("series") or {}).get("name") or "Tech explained").upper()
    f, lines = _fit(d, clean_title(script).upper(), 940, 5, 132)
    block = len(lines) * f.size * 1.08
    y0 = 700 - block / 2                       # inside the profile grid's centre crop
    d.text((70, y0 - 90), series, font=_font(40, "label"), fill=pal["signal"])
    _text_block(d, lines, f, 70, y0, pal["bone"], gap=1.08)
    d.rectangle([70, y0 + block + 30, 250, y0 + block + 42], fill=pal["signal"])
    d.text((70, 1700), "DATAVELVET", font=_font(36, "label"), fill=pal["ash"])
    img.save(out_path, quality=92)
    src.unlink(missing_ok=True)
    return str(out_path)


def carousel(video, script, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pal, times, scenes = _palette(script), scene_times(), script["scenes"]
    W, H = 1080, 1350

    def grab(i, k=0.75):
        a, b = times.get(i, (0, 1))
        return _frame(video, a + (b - a) * k, out_dir / f"src_{i}.png").resize((W, 1920))

    mid = list(range(1, len(scenes) - 1))
    keep = mid if len(mid) <= 4 else [mid[round(j * (len(mid) - 1) / 3)] for j in range(4)]
    total, slides = len(keep) + 3, []

    def page(d, n):
        d.text((W - 150, 50), f"{n}/{total}", font=_font(34, "label"), fill=pal["ash"])

    img = _band(Image.new("RGB", (W, H), pal["ink"]), grab(1), 600, 750, pal["ink"])     # 1: the hook (clean 3D frame)
    d = ImageDraw.Draw(img)
    f, lines = _fit(d, " ".join(scenes[0]["lines"]), 940, 4, 96)
    _text_block(d, lines, f, 70, 140, pal["bone"])
    d.text((70, 1200), "SWIPE  ->", font=_font(46, "label"), fill=pal["signal"])
    page(d, 1)
    slides.append(img)
    for n, i in enumerate(keep, 2):                                                       # the key steps
        img = Image.new("RGB", (W, H), pal["ink"])
        img.paste(_shade(grab(i).crop((0, 380, W, 380 + 760)), pal["ink"], 0.0, 0.55), (0, 0))
        d = ImageDraw.Draw(img)
        d.text((70, 800), f"{n - 1:02d}", font=_font(56, "head"), fill=pal["signal"])
        tf, tl = _fit(d, str(scenes[i].get("title", "")).upper(), 940, 2, 76)
        y = _text_block(d, tl, tf, 70, 880, pal["bone"])
        line = re.split(r"(?<=[.!?])\s+", " ".join(scenes[i]["lines"]))[0]
        bf, bl = _fit(d, line, 940, 4, 42, "body", 32)
        _text_block(d, bl, bf, 70, y + 24, pal["ash"], gap=1.3)
        page(d, n)
        slides.append(img)
    img = Image.new("RGB", (W, H), pal["ink"])                                            # cheat sheet
    d = ImageDraw.Draw(img)
    recap = (scenes[-1].get("data") or {}).get("recap") or [scenes[i].get("title", "") for i in keep][:3]
    d.text((70, 150), "CHEAT SHEET", font=_font(44, "label"), fill=pal["signal"])
    tf, tl = _fit(d, clean_title(script).upper(), 940, 3, 72)
    y = _text_block(d, tl, tf, 70, 230, pal["bone"]) + 60
    for k, r in enumerate(recap[:4], 1):
        d.text((70, y), f"{k:02d}", font=_font(48, "head"), fill=pal["signal"])
        bf, bl = _fit(d, str(r), 820, 2, 54, "head", 36)
        y = _text_block(d, bl, bf, 170, y + 2, pal["bone"]) + 40
    d.text((70, 1200), "SAVE THIS FOR LATER", font=_font(42, "label"), fill=pal["signal"])
    page(d, total - 1)
    slides.append(img)
    img = _band(Image.new("RGB", (W, H), pal["ink"]), grab(keep[-1] if keep else 1, 0.5), 650, 700, pal["ink"])   # follow
    d = ImageDraw.Draw(img)
    f, lines = _fit(d, "WATCH IT IN 3D ON OUR REELS", 940, 3, 96)
    y = _text_block(d, lines, f, 70, 420, pal["bone"])
    d.text((70, y + 40), "@datavelvet  ·  new tech explained every day", font=_font(40, "body"), fill=pal["ash"])
    d.rectangle([70, y + 120, 250, y + 132], fill=pal["signal"])
    page(d, total)
    slides.append(img)
    paths = []
    for k, im in enumerate(slides, 1):
        p = out_dir / f"slide_{k:02d}.jpg"
        im.save(p, quality=92)
        paths.append(str(p))
    for f in out_dir.glob("src_*.png"):
        f.unlink()
    return paths


def make_all(video, script, out_dir, cover_t=None):
    out_dir = Path(out_dir)
    tm = scene_times()
    k = min(2, len(script["scenes"]) - 1)               # a clean 3D moment (scene 3), not the hook's text
    if k in tm:
        cover_t = tm[k][0] + (tm[k][1] - tm[k][0]) * 0.75
    return reel_cover(video, script, out_dir / "cover.jpg", cover_t), carousel(video, script, out_dir / "carousel")
