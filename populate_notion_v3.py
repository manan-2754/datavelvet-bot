"""
Populate Notion DB from topics.json - WORKING VERSION for your keys
"""
import os, json, time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

NOTION_KEY = os.getenv("NOTION_API_KEY", "").strip()
DB_ID = os.getenv("NOTION_DATABASE_ID", "").strip()

if not NOTION_KEY or not DB_ID:
    print("ERROR: Set NOTION_API_KEY and NOTION_DATABASE_ID in .env")
    exit(1)

try:
    from notion_client import Client
except:
    os.system("pip install -q notion-client")
    from notion_client import Client

notion = Client(auth=NOTION_KEY)
topics_path = Path("topics.json")
topics = json.loads(topics_path.read_text())

print(f"Found {len(topics)} topics in topics.json")
print(f"Connecting to Notion DB: {DB_ID}")

# Test DB access
try:
    db = notion.databases.retrieve(database_id=DB_ID)
    title = db['title'][0]['plain_text'] if db['title'] else 'Untitled'
    print(f"✅ Connected to DB: {title}")
    print(f"Properties: {list(db['properties'].keys())}")
except Exception as e:
    print(f"❌ Failed to retrieve DB: {e}")
    print("Fix: In Notion, open DB -> ... -> Add connections -> Add your integration")
    exit(1)

# Check if DB already has data
existing = notion.databases.query(database_id=DB_ID, page_size=5)
print(f"DB currently has {len(existing['results'])} pages (sample)")

# Confirm
print(f"\nReady to add {len(topics)} topics to Notion...")
print("This will take ~60 seconds")

added = 0
failed = 0
for t in topics:
    try:
        notion.pages.create(
            parent={"database_id": DB_ID},
            properties={
                "Title": {"title": [{"text": {"content": t['title'][:100]}}]},
                "Language": {"select": {"name": t['language'][:30]}},
                "Code": {"rich_text": [{"text": {"content": t['code'][:1000]}}]},
                "Explanation": {"rich_text": [{"text": {"content": t['explanation'][:1000]}}]},
                "Category": {"select": {"name": t['category'][:30]}},
                "Used": {"checkbox": False}
            }
        )
        added += 1
        if added % 10 == 0:
            print(f"[{added}/{len(topics)}] Added...")
        time.sleep(0.35)
    except Exception as e:
        failed += 1
        print(f"Failed {t['title']}: {e}")
        if failed > 5:
            print("Too many failures, stopping")
            break

print(f"\n✅ Done! Added {added} topics, {failed} failed")
print(f"Your Notion now has {added} topics ready for bot")
print("\nNext: python main.py to test video generation")
