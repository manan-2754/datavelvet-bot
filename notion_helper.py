import json, random
from pathlib import Path
from config import USE_NOTION, NOTION_API_KEY, NOTION_DATABASE_ID

TOPICS_FILE = Path(__file__).parent / "topics.json"
USED_FILE = Path(__file__).parent / "used.json"
if not USED_FILE.exists():
    USED_FILE.write_text("[]")

def load_used():
    try: return set(json.loads(USED_FILE.read_text()))
    except: return set()

def save_used(s):
    USED_FILE.write_text(json.dumps(list(s), indent=2))

def get_topic_from_local():
    topics = json.loads(TOPICS_FILE.read_text())
    used = load_used()
    fresh = [t for t in topics if t['id'] not in used]
    if not fresh:
        print("All local topics used, resetting used.json")
        save_used(set())
        fresh = topics
    topic = random.choice(fresh)
    used.add(topic['id'])
    save_used(used)
    return topic

def get_topic_from_notion():
    try:
        from notion_client import Client
        notion = Client(auth=NOTION_API_KEY)
        # Try to query unused
        result = notion.databases.query(
            database_id=NOTION_DATABASE_ID,
            filter={"property": "Used", "checkbox": {"equals": False}},
            page_size=20
        )
        print(f"Notion query: found {len(result['results'])} unused topics")
        
        if not result['results']:
            # Check if DB is empty, then we need to populate
            all_count = notion.databases.query(database_id=NOTION_DATABASE_ID, page_size=1)
            if len(all_count['results']) == 0:
                print("Notion DB is empty! Run populate_notion_v3.py first")
                return get_topic_from_local()
            # Reset all to unused
            print("No unused topics, resetting all to unused...")
            all_pages = notion.databases.query(database_id=NOTION_DATABASE_ID, page_size=100)
            for page in all_pages['results']:
                try:
                    notion.pages.update(page_id=page['id'], properties={"Used": {"checkbox": False}})
                except:
                    pass
            result = notion.databases.query(
                database_id=NOTION_DATABASE_ID,
                filter={"property": "Used", "checkbox": {"equals": False}},
                page_size=20
            )
        
        if not result['results']:
            return get_topic_from_local()
        
        page = random.choice(result['results'])
        props = page['properties']
        
        def get_text(prop):
            try:
                if not prop:
                    return ""
                if prop['type'] == 'title':
                    return prop['title'][0]['plain_text'] if prop['title'] else ""
                if prop['type'] == 'rich_text':
                    return prop['rich_text'][0]['plain_text'] if prop['rich_text'] else ""
                if prop['type'] == 'select':
                    return prop['select']['name'] if prop['select'] else ""
                return ""
            except Exception as e:
                print(f"get_text error {e}")
                return ""
        
        # Mark as used
        try:
            notion.pages.update(page_id=page['id'], properties={"Used": {"checkbox": True}})
        except Exception as e:
            print(f"Failed to mark used: {e}")
        
        topic = {
            "id": page['id'],
            "language": get_text(props.get('Language', {})) or "Python",
            "title": get_text(props.get('Title', {})) or get_text(props.get('Name', {})) or "Coding trick",
            "code": get_text(props.get('Code', {})) or "print('hello')",
            "explanation": get_text(props.get('Explanation', {})) or "Useful trick",
            "category": get_text(props.get('Category', {})) or "tricks",
            "chart": None
        }
        print(f"Fetched from Notion: [{topic['language']}] {topic['title']}")
        return topic
        
    except Exception as e:
        print(f"Notion fetch failed: {e}")
        print("Falling back to local topics.json")
        return get_topic_from_local()

def get_next_topic():
    if USE_NOTION:
        return get_topic_from_notion()
    else:
        print("USE_NOTION=False, using local topics.json")
        return get_topic_from_local()
