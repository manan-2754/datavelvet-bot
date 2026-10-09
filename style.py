"""
Design DNA: every video gets a unique combination of palette, typography, background, shape language,
connector style, entrance motion, transition, caption and header style. Used combinations are remembered
in state.json so no video ever repeats a format or a colour combination.
"""
import colorsys
import hashlib
import json
import random

PALETTES = [  # name, bg, surface, text, muted, accents
    ("Midnight Citrus", "#0B0F1A", "#151B2D", "#F4F6FB", "#8A93A8", ["#FFB627", "#FF5D73", "#4ADEDE", "#7C5CFF"]),
    ("Paper & Ink", "#F4EFE6", "#FFFFFF", "#1C1B19", "#6F6A60", ["#E4572E", "#17BEBB", "#E0A800", "#2E282A"]),
    ("Electric Lime", "#0E0E10", "#1A1A1F", "#FAFAFA", "#8C8C99", ["#C6FF3D", "#3DDCFF", "#FF3D9A", "#FFFFFF"]),
    ("Ocean Dusk", "#06202B", "#0D3442", "#EAF6F6", "#86A9B0", ["#FF8C61", "#F9D56E", "#47B5FF", "#E86A92"]),
    ("Sakura", "#FFF5F7", "#FFFFFF", "#2B1B24", "#8B6B78", ["#FF5C8A", "#6C63FF", "#00B8A9", "#E09B00"]),
    ("Forest", "#0F1F17", "#183126", "#EEF5EF", "#8FAE98", ["#9BE564", "#F2C14E", "#4FB0C6", "#F78154"]),
    ("Royal", "#120B2E", "#1D1445", "#F5F3FF", "#9C93C9", ["#FFD166", "#EF476F", "#06D6A0", "#4CC9F0"]),
    ("Nordic", "#ECEFF4", "#FFFFFF", "#2E3440", "#6B7385", ["#5E81AC", "#BF616A", "#6E9A55", "#D08770"]),
    ("Mono Red", "#111111", "#1E1E1E", "#FFFFFF", "#9A9A9A", ["#FF3B30", "#FF9F0A", "#FFFFFF", "#5AC8FA"]),
    ("Sunset Synth", "#1A0B2E", "#2A1446", "#FFF1F8", "#B79CC9", ["#FF6EC7", "#FFB347", "#7DF9FF", "#9D4EDD"]),
    ("Mint Cream", "#F1FAF5", "#FFFFFF", "#12342A", "#5E7D72", ["#00A878", "#FF6B6B", "#4D9DE0", "#D98E04"]),
    ("Terracotta", "#FBF3EA", "#FFFFFF", "#2D1E17", "#8A6F60", ["#D9603B", "#2A9D8F", "#C98A1B", "#264653"]),
    ("Cyber Teal", "#021619", "#08292E", "#E6FFFB", "#7FB2AD", ["#00F5D4", "#F15BB5", "#FEE440", "#9B5DE5"]),
    ("Graphite Gold", "#18181B", "#27272A", "#FAFAF9", "#A1A1AA", ["#EAB308", "#F97316", "#E4E4E7", "#22D3EE"]),
    ("Blueprint", "#0A2A5E", "#103877", "#EAF2FF", "#9DB6E0", ["#FFFFFF", "#FFD23F", "#5CE1E6", "#FF6B6B"]),
    ("Lavender Fog", "#F3F0FF", "#FFFFFF", "#241F3A", "#6E6890", ["#7048E8", "#F76707", "#12B886", "#E64980"]),
    ("Volcano", "#1B0E0A", "#2B1711", "#FFF4EE", "#B89585", ["#FF5722", "#FFC107", "#FF8A65", "#4DD0E1"]),
    ("Arctic", "#E8F4FA", "#FFFFFF", "#0B2738", "#557086", ["#0077B6", "#F72585", "#169C8F", "#F08A00"]),
    ("Emerald Night", "#031B16", "#0A2E26", "#EAFBF5", "#7FAE9F", ["#34D399", "#FBBF24", "#60A5FA", "#F472B6"]),
    ("Retro Pop", "#FFF8E7", "#FFFFFF", "#1F1A17", "#7A6E62", ["#FF4F4F", "#2D7FF9", "#E09A00", "#1FB58F"]),
    ("Ink Blue", "#0D1B2A", "#1B263B", "#E0E1DD", "#8D99AE", ["#F4A261", "#E76F51", "#2A9D8F", "#E9C46A"]),
    ("Neon Noir", "#070708", "#141417", "#F2F2F2", "#838390", ["#00E5FF", "#FF2E88", "#FFE600", "#7CFF6B"]),
    ("Peach", "#FFF1EA", "#FFFFFF", "#2A1A14", "#8C6B5E", ["#FF7B54", "#6A4C93", "#1982C4", "#6FA81E"]),
    ("Steel", "#1F2933", "#323F4B", "#F5F7FA", "#9AA5B1", ["#FF6B6B", "#FFD93D", "#6BCB77", "#4D96FF"]),
    ("Matcha", "#EEF2E3", "#FFFFFF", "#1E2A16", "#66745A", ["#5A8F29", "#D1495B", "#00798C", "#D9962B"]),
    ("Deep Space", "#05060F", "#10132A", "#EEF0FF", "#8890C0", ["#8B5CF6", "#22D3EE", "#F43F5E", "#FACC15"]),
    ("Coral Reef", "#08233A", "#0E3354", "#F0F8FF", "#8FB3CF", ["#FF6F59", "#43AA8B", "#FFD166", "#B388EB"]),
    ("Sand", "#F5EBDD", "#FFFDF8", "#2B2118", "#857360", ["#C2410C", "#0F766E", "#B45309", "#1D4ED8"]),
    ("Berry", "#1E0B1A", "#31142B", "#FFF0FA", "#C29AB7", ["#F72585", "#4CC9F0", "#FFD60A", "#80ED99"]),
    ("Clean White", "#FAFAFA", "#FFFFFF", "#111827", "#6B7280", ["#2563EB", "#F59E0B", "#10B981", "#EF4444"]),
]

FONT_PAIRS = [  # title, body, mono
    ("SpaceGrotesk-Bold", "Inter-Medium", "JetBrainsMono-Regular"),
    ("Sora-Bold", "Inter-Regular", "JetBrainsMono-Regular"),
    ("Manrope-ExtraBold", "Manrope-Medium", "JetBrainsMono-Regular"),
    ("DMSerifDisplay-Regular", "Inter-Medium", "JetBrainsMono-Regular"),
    ("Outfit-Bold", "Outfit-Regular", "JetBrainsMono-Regular"),
    ("Inter-SemiBold", "Inter-Regular", "JetBrainsMono-SemiBold"),
    ("ArchivoBlack-Regular", "Inter-Medium", "JetBrainsMono-Regular"),
    ("PlusJakarta-ExtraBold", "PlusJakarta-Medium", "JetBrainsMono-Regular"),
]

OPTIONS = {
    "bg_pattern": ["dots", "grid", "diagonal", "rings", "waves", "crosses", "gradient", "halftone"],
    "shape": ["rounded", "sharp", "pill", "cut", "soft"],
    "connector": ["curve", "elbow", "straight", "flow"],
    "entrance": ["pop", "slide", "grow", "flip", "drop"],
    "transition": ["wipe_h", "wipe_v", "diagonal", "iris", "blinds", "split"],
    "caption": ["pill", "underline", "bold", "boxed"],
    "header": ["kicker", "centered", "bignum", "chip"],
    "shadow": ["flat", "none", "outline"],
    "motion": ["snappy", "smooth", "bouncy"],
    "light": ["left", "right", "top"],                     # direction of 3D extrusion and shading
    "depth": ["shallow", "deep", "long"],                  # how far 3D labels and cards extrude
    "prim": ["tri", "box", "hex", "oct", "round"],         # base primitive of 3D diagram objects
    "cam": ["orbit", "sway", "crane", "dolly", "dutch"],   # real-time camera move in 3D scenes
    "render3d": ["holo", "neon", "blueprint"],            # hologram style (glass hatch / neon glow / blueprint)
    "floor": ["rings", "radar", "grid", "hex"],            # holographic floor
}


def hex2rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rotate_hue(rgb, deg):
    r, g, b = [c / 255 for c in rgb]
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    r, g, b = colorsys.hls_to_rgb((h + deg / 360) % 1, l, s)
    return (int(r * 255), int(g * 255), int(b * 255))


def palette(pid, rot=0):
    name, bg, surf, text, muted, acc = PALETTES[pid]
    accents = [hex2rgb(a) for a in acc]
    if rot:
        accents = [rotate_hue(a, rot) for a in accents]
    return {"name": name + (f" +{rot}deg" if rot else ""), "bg": hex2rgb(bg), "surface": hex2rgb(surf),
            "text": hex2rgb(text), "muted": hex2rgb(muted), "accents": accents, "light": sum(hex2rgb(bg)) > 382}


def signature(dna, layouts):
    key = json.dumps({k: dna[k] for k in sorted(dna) if k != "seed"}, sort_keys=True) + "|" + ",".join(layouts)
    return hashlib.sha1(key.encode()).hexdigest()[:16]


def new_dna(state, seed=None):
    """Pick an unused palette (+hue rotation once all are used) and a never-used combination of style options."""
    rng = random.Random(seed)
    used_pal = set(state.get("used_palettes", []))
    used_combo = set(state.get("used_combos", []))
    pid, rot = None, 0
    for rot in (0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330):
        free = [i for i in range(len(PALETTES)) if f"{i}:{rot}" not in used_pal]
        if free:
            pid = rng.choice(free)
            break
    if pid is None:
        pid, rot = rng.randrange(len(PALETTES)), rng.randrange(1, 360)
    dna = {}
    for _ in range(500):
        dna = {k: rng.choice(v) for k, v in OPTIONS.items()}
        dna["fonts"] = rng.randrange(len(FONT_PAIRS))
        if json.dumps(dna, sort_keys=True) not in used_combo:
            break
    dna.update(palette=pid, rot=rot, seed=rng.randrange(10 ** 9))
    return dna


def remember(state, dna, layouts):
    state.setdefault("used_palettes", []).append(f"{dna['palette']}:{dna['rot']}")
    combo = {k: v for k, v in dna.items() if k not in ("palette", "rot", "seed")}
    state.setdefault("used_combos", []).append(json.dumps(combo, sort_keys=True))
    state.setdefault("used_signatures", []).append(signature(dna, layouts))
    state.setdefault("used_layout_seqs", []).append(",".join(layouts))
