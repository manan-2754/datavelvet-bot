import os
from dotenv import load_dotenv
load_dotenv()

# --- NOTION ---
NOTION_API_KEY = os.getenv("NOTION_API_KEY", "").strip()
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID", "").strip()
USE_NOTION = bool(NOTION_API_KEY and NOTION_DATABASE_ID)

# --- GEMINI ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

# --- SETTINGS ---
USE_REAL_IMAGES = os.getenv("USE_REAL_IMAGES", "True").lower() == "true"
AUTO_POST_YOUTUBE = os.getenv("AUTO_POST_YOUTUBE", "false").lower() == "true"
AUTO_POST_INSTAGRAM = os.getenv("AUTO_POST_INSTAGRAM", "false").lower() == "true"

VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
FPS = 24

LANGUAGES = ["Python", "JavaScript", "Java", "C++", "Go", "Rust", "TypeScript", "SQL", "Data Science", "AI Ethics"]

print(f"Config loaded: USE_NOTION={USE_NOTION}, USE_REAL_IMAGES={USE_REAL_IMAGES}, GEMINI={'SET' if GEMINI_API_KEY else 'NOT SET'}")
