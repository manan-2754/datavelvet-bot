"""
High Motion Graphics Engine v3 - FIXED for Pillow 10+ and no ImageMagick
- Typing animation with cursor
- Syntax highlight
- Chart animation
- Language badge + Title + Captions all via Pillow (no TextClip)
"""
from pathlib import Path
import PIL.Image
# FIX for Pillow 10+ where ANTIALIAS was removed - moviepy 1.0.3 still uses it
if not hasattr(PIL.Image, 'ANTIALIAS'):
    try:
        PIL.Image.ANTIALIAS = PIL.Image.Resampling.LANCZOS
    except:
        PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

from PIL import Image, ImageDraw, ImageFont
import math, random
from moviepy.editor import ImageClip, ColorClip, CompositeVideoClip, ImageSequenceClip, AudioFileClip
import os

W, H = 1080, 1920

def get_font(size=28, bold=False):
    try:
        if bold:
            return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", size)
    except:
        try:
            return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)
        except:
            # Windows fallback
            try:
                if bold:
                    return ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", size)
                return ImageFont.truetype("C:/Windows/Fonts/consola.ttf", size)
            except:
                return ImageFont.load_default()

def create_text_image(text, width=900, fontsize=48, color=(255,255,255), bg_color=None, bold=False, max_lines=5):
    """Create PIL image with text, no ImageMagick needed"""
    font = get_font(fontsize, bold=bold)
    import textwrap
    avg_char_width = fontsize * 0.6
    chars_per_line = max(10, int(width / avg_char_width))
    lines = []
    for paragraph in text.split('\n'):
        wrapped = textwrap.wrap(paragraph, width=chars_per_line)
        if not wrapped:
            lines.append("")
        else:
            lines.extend(wrapped)
    
    lines = lines[:max_lines]
    line_height = fontsize + 12
    img_height = len(lines) * line_height + 30
    
    if bg_color:
        img = Image.new('RGBA', (width, img_height), bg_color)
    else:
        img = Image.new('RGBA', (width, img_height), (0,0,0,0))
    
    draw = ImageDraw.Draw(img)
    y = 15
    for line in lines:
        # Use stroke for readability
        try:
            draw.text((15, y), line, font=font, fill=color, stroke_width=2, stroke_fill=(0,0,0))
        except TypeError:
            # Older Pillow without stroke
            draw.text((15, y), line, font=font, fill=color)
        y += line_height
    
    return img

def create_typing_frames(code_text, duration, fps=20):
    total_chars = len(code_text)
    num_frames = int(duration * fps)
    frames = []
    for f in range(num_frames):
        progress = f / num_frames
        eased = 1 - pow(1 - progress, 3)
        chars_to_show = int(total_chars * eased)
        img = Image.new('RGB', (900, 650), color=(22,22,28))
        draw = ImageDraw.Draw(img)
        draw.rectangle([0,0,900,40], fill=(45,45,50))
        draw.ellipse([15,12,28,25], fill=(255,95,87))
        draw.ellipse([35,12,48,25], fill=(255,189,46))
        draw.ellipse([55,12,68,25], fill=(39,201,63))
        font = get_font(20)
        visible = code_text[:chars_to_show]
        cursor = "█" if (f // 6) % 2 == 0 else ""
        visible += cursor
        y = 60
        for line in visible.split('\n')[:18]:
            color = (0,255,150)
            if any(k in line for k in ['def ','import','from','const','let','var','func','type','SELECT','let ','auto','record','defer']):
                color = (86,156,214)
            if '//' in line or '#' in line or '--' in line:
                color = (106,153,85)
            draw.text((20, y), line[:85], font=font, fill=color)
            y += 30
        frames.append(img)
    return frames

def create_chart_frames(chart_data, duration, fps=20):
    if not chart_data:
        return None
    labels = chart_data.get('labels', ['A','B','C'])
    values = chart_data.get('values', [30,60,90])
    max_val = max(values) if values else 100
    num_frames = int(duration * fps)
    frames = []
    for f in range(num_frames):
        progress = f / num_frames
        eased = 1 - pow(1 - progress, 2)
        img = Image.new('RGB', (900, 500), color=(22,22,28))
        draw = ImageDraw.Draw(img)
        font = get_font(20, bold=True)
        font_small = get_font(16)
        draw.text((20,20), "Data Visualization", font=font, fill=(255,255,255))
        bar_width = 180
        gap = 60
        x_start = 60
        y_base = 420
        for i, (label, val) in enumerate(zip(labels, values)):
            bar_h = int((val / max_val) * 300 * eased)
            x = x_start + i*(bar_width+gap)
            y_top = y_base - bar_h
            draw.rectangle([x, y_top, x+bar_width, y_base], fill=(0,255,150))
            draw.text((x+20, y_top-25), f"{int(val*eased)}", font=font_small, fill=(255,255,255))
            draw.text((x+20, y_base+10), label, font=font_small, fill=(180,180,180))
        frames.append(img)
    return frames

def create_high_motion_video(audio_path, topic, script, output_path, background_image_path=None):
    # Patch PIL again inside function for moviepy
    import PIL.Image
    if not hasattr(PIL.Image, 'ANTIALIAS'):
        try:
            PIL.Image.ANTIALIAS = PIL.Image.Resampling.LANCZOS
        except:
            PIL.Image.ANTIALIAS = PIL.Image.LANCZOS
    
    audio = AudioFileClip(str(audio_path))
    duration = min(audio.duration + 0.8, 58)
    clips = []
    
    # Background
    if background_image_path and Path(background_image_path).exists():
        try:
            bg = ImageClip(str(background_image_path)).set_duration(duration).resize((W,H))
            # Use lambda with no ANTIALIAS issue - moviepy will handle
            bg = bg.resize(lambda t: 1 + 0.02*t)
            clips.append(bg)
            overlay = ColorClip(size=(W,H), color=(0,0,0), duration=duration).set_opacity(0.6)
            clips.append(overlay)
        except Exception as e:
            print(f"BG clip failed {e}, using solid")
            bg = ColorClip(size=(W,H), color=(13,13,18), duration=duration)
            clips.append(bg)
    else:
        bg = ColorClip(size=(W,H), color=(13,13,18), duration=duration)
        clips.append(bg)
    
    # Language badge via Pillow
    try:
        lang = topic.get('language','Python')
        badge_img = create_text_image(f"  {lang}  ", width=300, fontsize=38, color=(0,0,0), bg_color=(0,255,150,255), bold=True, max_lines=1)
        badge_path = Path("output/temp_badge.png")
        badge_img.save(badge_path)
        badge_clip = ImageClip(str(badge_path)).set_duration(duration).set_position((60, 80))
        clips.append(badge_clip)
    except Exception as e:
        print(f"Badge failed {e}")
    
    # Title via Pillow
    try:
        title_img = create_text_image(topic['title'], width=950, fontsize=52, color=(255,255,255), bold=True, max_lines=3)
        title_path = Path("output/temp_title.png")
        title_img.save(title_path)
        title_clip = ImageClip(str(title_path)).set_duration(duration).set_position(('center', 170))
        clips.append(title_clip)
    except Exception as e:
        print(f"Title failed {e}")
    
    # Typing animation
    if topic.get('code'):
        typing_duration = duration * 0.65
        frames = create_typing_frames(topic['code'], typing_duration, fps=20)
        temp_dir = Path("output/temp_frames")
        temp_dir.mkdir(parents=True, exist_ok=True)
        paths = []
        for idx, img in enumerate(frames[::2]):
            p = temp_dir / f"f_{idx:04d}.png"
            img.save(p)
            paths.append(str(p))
        if paths:
            typing_clip = ImageSequenceClip(paths, fps=12).set_duration(typing_duration).set_position(('center', 380)).resize(width=900)
            clips.append(typing_clip)
    
    # Chart for data science
    if topic.get('chart'):
        chart_frames = create_chart_frames(topic['chart'], duration*0.35)
        if chart_frames:
            temp_dir = Path("output/temp_chart")
            temp_dir.mkdir(parents=True, exist_ok=True)
            c_paths = []
            for idx, img in enumerate(chart_frames[::2]):
                p = temp_dir / f"c_{idx:04d}.png"
                img.save(p)
                c_paths.append(str(p))
            if c_paths:
                chart_clip = ImageSequenceClip(c_paths, fps=12).set_duration(duration*0.35).set_position(('center', 1100)).resize(width=900)
                clips.append(chart_clip)
    
    # Captions via Pillow
    try:
        import textwrap
        words = script.split()
        chunk = 9
        num_chunks = max(1, len(words)//chunk)
        for i in range(0, len(words), chunk):
            start = (i//chunk) * (duration / (num_chunks+1))
            txt = " ".join(words[i:i+chunk])
            cap_img = create_text_image(txt, width=900, fontsize=44, color=(255,255,0), bold=True, max_lines=2)
            cap_path = Path(f"output/temp_cap_{i}.png")
            cap_img.save(cap_path)
            cap_clip = ImageClip(str(cap_path)).set_duration(duration/(num_chunks+1)).set_position(('center', 1380)).set_start(start)
            clips.append(cap_clip)
    except Exception as e:
        print(f"Caption failed {e}")
    
    final = CompositeVideoClip(clips).set_audio(audio)
    final.write_videofile(str(output_path), fps=24, codec='libx264', audio_codec='aac', threads=2, logger=None)
    print(f"✅ Video saved: {output_path}")
    
    import shutil
    shutil.rmtree("output/temp_frames", ignore_errors=True)
    shutil.rmtree("output/temp_chart", ignore_errors=True)
    for f in Path("output").glob("temp_*.png"):
        try: f.unlink()
        except: pass
