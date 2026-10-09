"""
Human touch: mix your own short clips into the videos.

Drop vertical clips (a phone selfie video is perfect, 2-6 seconds) into:
  assets/human/intro/   - played before the video (keep these VERY short, ~2s, or they hurt the hook)
  assets/human/outro/   - played after the end card ("If this helped, follow - I post every day")
The bot picks a different clip each time. No clips -> videos are unchanged.
"""
import random
import re
import subprocess
from pathlib import Path

from explainer_engine import ffmpeg_exe

BASE = Path(__file__).parent / "assets" / "human"
EXTS = {".mp4", ".mov", ".m4v", ".webm"}


def _clips(kind):
    folder = BASE / kind
    return sorted(p for p in folder.glob("*") if p.suffix.lower() in EXTS) if folder.exists() else []


def _probe(path):
    """(has_audio, duration_seconds) from ffmpeg's banner."""
    err = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", str(path)], capture_output=True, text=True).stderr
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err)
    dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0
    return "Audio:" in err, dur


def add_human_clips(video, width, height, seed=None):
    """Return the path of the video with an intro and/or outro clip of you added (or the original path)."""
    rng = random.Random(seed)
    intros, outros = _clips("intro"), _clips("outro")
    intro = rng.choice(intros) if intros else None
    outro = rng.choice(outros) if outros else None
    if not intro and not outro:
        return video
    parts = [p for p in (intro, video, outro) if p]
    cmd = [ffmpeg_exe(), "-y", "-loglevel", "error"]
    for p in parts:
        cmd += ["-i", str(p)]
    filters, labels = [], []
    for i, p in enumerate(parts):
        has_audio, dur = _probe(p)
        filters.append(f"[{i}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
                       f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,fps=30,format=yuv420p,setsar=1[v{i}]")
        if has_audio:
            filters.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo[a{i}]")
        else:
            filters.append(f"aevalsrc=0:c=stereo:s=48000:d={dur:.3f}[a{i}]")
        labels.append(f"[v{i}][a{i}]")
    filters.append("".join(labels) + f"concat=n={len(parts)}:v=1:a=1[v][a]")
    out = Path(video).with_name("video_human.mp4")
    cmd += ["-filter_complex", ";".join(filters), "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart", str(out)]
    subprocess.run(cmd, check=True)
    added = " + ".join(x for x in (f"intro {intro.name}" if intro else "", f"outro {outro.name}" if outro else "") if x)
    print(f"  human touch: added {added}")
    return out
