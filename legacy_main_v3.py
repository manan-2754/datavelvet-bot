"""
v3 WORKING - FIXED VERSION - No ANTIALIAS error, working TTS fallback, Gemini fallback
"""
import asyncio, json, random, time, requests, os, sys
from pathlib import Path

# FIX Pillow 10+ ANTIALIAS issue BEFORE importing moviepy
import PIL.Image
if not hasattr(PIL.Image, 'ANTIALIAS'):
    try:
        PIL.Image.ANTIALIAS = PIL.Image.Resampling.LANCZOS
    except:
        PIL.Image.ANTIALIAS = PIL.Image.LANCZOS
    print("✅ Fixed PIL ANTIALIAS for Pillow 10+")

from dotenv import load_dotenv
load_dotenv()

from notion_helper import get_next_topic
from config import USE_REAL_IMAGES, GEMINI_API_KEY
from motion_graphics import create_high_motion_video

BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

def download_bg(prompt, save_path):
    if not USE_REAL_IMAGES:
        return False
    try:
        encoded = requests.utils.quote(prompt)
        url = f"https://image.pollinations.ai/prompt/{encoded}?width=1080&height=1920&nologo=true&seed={random.randint(1,999999)}"
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        save_path.write_bytes(r.content)
        print(f"✅ BG downloaded")
        return True
    except Exception as e:
        print(f"BG download failed: {e}, using solid color")
        return False

def gen_script(topic):
    # Fallback viral template - works without Gemini
    hooks = {
        "Python": "Stop coding Python like a beginner!",
        "JavaScript": "Senior JS devs hide this trick!",
        "Data Science": "This Data Science trick saves 10 hours!",
        "AI Ethics": "Is your code ethical? Listen to this!",
        "Go": "Go devs don't want you to know this!",
        "Rust": "Rust trick that prevents 100 bugs!",
        "SQL": "SQL trick 90% of devs don't know!",
        "Java": "Java trick that saves 20 lines!",
        "C++": "C++ trick that changes everything!",
        "TypeScript": "TypeScript trick that catches 100 bugs!"
    }
    hook = hooks.get(topic['language'], "Stop coding like a junior!")
    fallback = f"{hook} {topic['title']}. {topic['explanation']}. Look at this code. This one trick will save you hours. Save this video and follow for more {topic['language']} tricks they don't teach in school."
    
    if not GEMINI_API_KEY or "Your" in GEMINI_API_KEY or len(GEMINI_API_KEY) < 20:
        print("No valid GEMINI_API_KEY, using viral template (works fine)")
        return fallback
    
    # Try Gemini with proper error handling
    try:
        print(f"Trying Gemini...")
        # Try multiple models
        models = ["gemini-1.5-flash", "gemini-1.0-pro", "gemini-pro"]
        for model in models:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
                prompt = f"Write viral 35-sec YouTube Shorts script for {topic['language']}. Title: {topic['title']} Code: {topic['code']} Explanation: {topic['explanation']} Rules: Start with strong hook, 130 words max, explain code simply, end with CTA Follow for more, just script."
                payload = {"contents": [{"parts": [{"text": prompt}]}]}
                r = requests.post(url, json=payload, timeout=15)
                if r.status_code == 200:
                    data = r.json()
                    text = data['candidates'][0]['content']['parts'][0]['text'].strip()
                    print(f"✅ Gemini script generated with {model}")
                    return text
                else:
                    print(f"Gemini {model} failed {r.status_code}: {r.text[:200]}")
            except Exception as e:
                print(f"Gemini {model} error: {e}")
                continue
        
        print("All Gemini models failed, using fallback template")
        return fallback
    except Exception as e:
        print(f"Gemini error: {e}, using fallback")
        return fallback

async def tts_edge(text, path):
    """Try edge-tts"""
    try:
        import edge_tts
        voices = ["en-US-GuyNeural", "en-US-JennyNeural", "en-CA-ClaraNeural"]
        voice = random.choice(voices)
        print(f"TTS trying edge-tts voice {voice}...")
        comm = edge_tts.Communicate(text, voice)
        await comm.save(str(path))
        if path.exists() and path.stat().st_size > 1000:
            print(f"✅ edge-tts saved: {path}")
            return True
    except Exception as e:
        print(f"edge-tts failed: {e}")
    return False

def tts_gtts(text, path):
    """Fallback to gTTS - Google free TTS, no key needed"""
    try:
        from gtts import gTTS
        print(f"TTS trying gTTS...")
        tts = gTTS(text=text, lang='en', slow=False)
        tts.save(str(path))
        if path.exists() and path.stat().st_size > 1000:
            print(f"✅ gTTS saved: {path}")
            return True
    except Exception as e:
        print(f"gTTS failed: {e}")
    return False

def tts_pyttsx3(text, path):
    """Fallback to pyttsx3 offline"""
    try:
        import pyttsx3
        print(f"TTS trying pyttsx3 offline...")
        engine = pyttsx3.init()
        engine.setProperty('rate', 180)
        engine.save_to_file(text, str(path))
        engine.runAndWait()
        if path.exists() and path.stat().st_size > 1000:
            print(f"✅ pyttsx3 saved: {path}")
            return True
    except Exception as e:
        print(f"pyttsx3 failed: {e}")
    return False

async def tts(text, path):
    # Try edge-tts first
    if await tts_edge(text, path):
        return True
    # Then gTTS
    if tts_gtts(text, path):
        return True
    # Then pyttsx3
    if tts_pyttsx3(text, path):
        return True
    
    print("All TTS failed, creating silent audio...")
    try:
        from moviepy.editor import AudioClip
        def make_frame(t): return [0,0]
        silent = AudioClip(make_frame, duration=35)
        silent.write_audiofile(str(path), fps=44100, logger=None)
        print(f"✅ Silent audio created: {path}")
        return True
    except Exception as e:
        print(f"Silent audio also failed: {e}")
        return False

def gen_meta(topic, script):
    title = f"{topic['title']} | {topic['language']} in 30 sec"
    desc = f"""{script}

Learn {topic['language']} in 30-sec videos.
Code: {topic['code'][:200]}

Follow for daily {topic['language']} tricks.

#coding #programming #{topic['language'].lower().replace(' ','')} #learntocode #shorts #darkcode #datascience #aiethics #waterloo
"""
    return {"title": title[:95], "description": desc, "tags": [topic['language'].lower(), "coding", "programming", "learn to code"]}

async def main():
    print("="*60)
    print("v3 WORKING - Universal Programming Video Factory - FIXED")
    print("="*60)
    
    topic = get_next_topic()
    print(f"\n📌 Topic: [{topic['language']}] {topic['title']}")
    print(f"Code: {topic['code'][:100]}...")
    
    script = gen_script(topic)
    print(f"\n📝 Script ({len(script.split())} words): {script[:250]}...")
    
    ts = int(time.time())
    audio_path = OUTPUT_DIR / f"voice_{ts}.mp3"
    video_path = OUTPUT_DIR / f"video_{ts}.mp4"
    meta_path = OUTPUT_DIR / f"meta_{ts}.json"
    bg_path = OUTPUT_DIR / f"bg_{ts}.jpg"
    
    # 1. Background
    prompts = {
        "Python": "photorealistic programmer desk with Python code on 3 monitors, RGB lights, cinematic 8k, dark",
        "JavaScript": "photorealistic JavaScript developer workspace, dark room, code on screen, cinematic 8k",
        "Data Science": "photorealistic data science lab with charts on screens, futuristic, 8k dark",
        "AI Ethics": "photorealistic AI ethics concept, robot and human, dark office, cinematic 8k",
        "Go": "photorealistic Go programming setup, gopher logo, dark modern office, cinematic",
        "Rust": "photorealistic Rust programming, dark desk with crab logo, cinematic",
        "SQL": "photorealistic SQL database visualization, dark server room, cinematic",
    }
    prompt = prompts.get(topic['language'], f"photorealistic {topic['language']} coding setup, cinematic 8k, dark, 9:16")
    has_bg = download_bg(prompt, bg_path)
    
    # 2. TTS with multiple fallbacks
    print(f"\n🔊 Generating voice...")
    tts_ok = await tts(script, audio_path)
    if not tts_ok or not audio_path.exists() or audio_path.stat().st_size < 1000:
        print("❌ Audio generation failed, cannot continue")
        return
    
    # 3. Video
    print(f"\n🎬 Creating high motion graphics video...")
    try:
        create_high_motion_video(audio_path, topic, script, video_path, bg_path if has_bg else None)
    except Exception as e:
        print(f"❌ High motion failed: {e}")
        import traceback
        traceback.print_exc()
        print("Trying simple fallback video...")
        try:
            from moviepy.editor import ColorClip, AudioFileClip
            audio = AudioFileClip(str(audio_path))
            bg = ColorClip(size=(1080,1920), color=(13,13,18), duration=audio.duration+0.5)
            final = bg.set_audio(audio)
            final.write_videofile(str(video_path), fps=24, codec='libx264', audio_codec='aac', logger=None)
            print(f"✅ Fallback video created: {video_path}")
        except Exception as e2:
            print(f"❌ Fallback also failed: {e2}")
            return
    
    # 4. Meta
    meta = gen_meta(topic, script)
    meta.update({"topic": topic, "script": script, "video_file": video_path.name, "audio_file": audio_path.name})
    meta_path.write_text(json.dumps(meta, indent=2))
    
    print("\n" + "="*60)
    print("✅ DONE!")
    print(f"Video: {video_path}")
    print(f"Meta: {meta_path}")
    if video_path.exists():
        print(f"Size: {video_path.stat().st_size / 1024 / 1024:.2f} MB")
    print("="*60)
    print("\nNext steps:")
    print("1. Check video: output/video_*.mp4")
    print("2. Upload to YouTube Shorts + IG Reels + TikTok with description from meta.json")
    print("3. For auto-post, set up youtube_upload.py and GitHub Actions")

if __name__ == "__main__":
    asyncio.run(main())
