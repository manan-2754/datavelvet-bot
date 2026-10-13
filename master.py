"""Finishing pass, after OpenMontage's approach (own implementation, plain FFmpeg):
broadcast-style voice mastering to the -14 LUFS that YouTube and Instagram normalise to, and a pre-post QA gate
(ffprobe validation, black / frozen frames, dead air, loudness) so a broken render never gets uploaded."""
import json
import re
import subprocess
from pathlib import Path

import audio_build

LUFS, TP, LRA = -14.0, -1.0, 9.0


def _ff(*args):
    return subprocess.run([audio_build.ffmpeg(), "-hide_banner", "-nostats", *map(str, args)], check=True,
                          capture_output=True, text=True, encoding="utf-8", errors="replace")


def master(wav):
    """Highpass + de-ess + gentle glue compression, then two-pass loudnorm to -14 LUFS / -1 dBTP."""
    wav = Path(wav)
    chain = "highpass=f=70,deesser=i=0.35,acompressor=threshold=-21dB:ratio=2.5:attack=8:release=120:makeup=1.5"
    try:
        r = _ff("-i", wav, "-af", f"{chain},loudnorm=I={LUFS}:TP={TP}:LRA={LRA}:print_format=json", "-f", "null", "-")
        m = json.loads(r.stderr[r.stderr.rindex("{"):r.stderr.rindex("}") + 1])
        out = wav.with_name(wav.stem + "_master.wav")
        _ff("-y", "-v", "error", "-i", wav, "-af",
            f"{chain},loudnorm=I={LUFS}:TP={TP}:LRA={LRA}:measured_I={m['input_i']}:measured_TP={m['input_tp']}"
            f":measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true",
            "-ar", "48000", "-ac", "2", out)
        print(f"  mastered: {float(m['input_i']):.1f} -> {LUFS:.0f} LUFS")
        return out
    except Exception as e:
        print(f"  mastering skipped ({str(e)[:120]})")
        return wav


def qa(video, expect_dur=None):
    """Inspect the finished file. Returns {"ok", "issues", ...}; ok=False only for faults worth not posting."""
    video, issues, hard = Path(video), [], []
    ffprobe = str(Path(audio_build.ffmpeg()).with_name(Path(audio_build.ffmpeg()).name.replace("ffmpeg", "ffprobe")))
    p = json.loads(subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height",
                                   "-of", "json", str(video)], capture_output=True, text=True, check=True).stdout)
    kinds = {s["codec_type"] for s in p["streams"]}
    dur = float(p["format"]["duration"])
    v = next(s for s in p["streams"] if s["codec_type"] == "video")
    if "audio" not in kinds:
        hard.append("no audio track")
    if expect_dur and abs(dur - expect_dur) > 1.0:
        issues.append(f"duration {dur:.1f}s vs {expect_dur:.1f}s expected")
    r = _ff("-i", video, "-vf", "blackdetect=d=0.5:pix_th=0.06,freezedetect=n=0.001:d=2.5", "-af",
            "silencedetect=n=-45dB:d=1.8,ebur128=peak=true", "-f", "null", "-").stderr
    black = sum(float(x) for x in re.findall(r"black_duration:([\d.]+)", r))
    freezes = [float(x) for x in re.findall(r"freeze_duration: ([\d.]+)", r)]
    silences = [float(x) for x in re.findall(r"silence_duration: ([\d.]+)", r)]
    lufs = re.findall(r"I:\s+(-?[\d.]+) LUFS", r)
    lufs = float(lufs[-1]) if lufs else None
    if black > 0.15 * dur:
        hard.append(f"{black:.1f}s of black frames")
    elif black > 1.0:
        issues.append(f"{black:.1f}s black")
    if freezes and max(freezes) > 6:
        hard.append(f"picture frozen for {max(freezes):.1f}s")
    elif freezes:
        issues.append(f"longest still {max(freezes):.1f}s")
    if silences and max(silences) > 4:
        hard.append(f"{max(silences):.1f}s of dead air")
    if lufs is not None and abs(lufs - LUFS) > 3:
        issues.append(f"loudness {lufs:.1f} LUFS")
    res = {"ok": not hard, "issues": hard + issues, "duration": round(dur, 2), "size": f"{v['width']}x{v['height']}",
           "lufs": lufs, "black_s": round(black, 2), "longest_still_s": max(freezes, default=0), "longest_silence_s": max(silences, default=0)}
    print(f"  🔎 QA {'passed' if res['ok'] else 'FAILED'}: {res['size']}, {dur:.1f}s, "
          f"{lufs if lufs is not None else '?'} LUFS" + (f" - {'; '.join(res['issues'])}" if res["issues"] else ""))
    return res
