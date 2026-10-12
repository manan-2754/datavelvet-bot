"""
Waits until a local clock time today in Eastern Time (America/Toronto, so daylight saving is handled), so a video that
was made early posts exactly on schedule. GitHub starts scheduled jobs late (sometimes hours), so the workflows start
hours before the slot, prepare and render, then call this right before uploading.

  python wait_until.py 13:00
"""
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

if __name__ == "__main__":
    hh, mm = map(int, sys.argv[1].split(":"))
    now = datetime.now(ZoneInfo("America/Toronto"))
    target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    wait = (target - now).total_seconds()
    if 0 < wait < 8 * 3600:
        print(f"⏳ Video ready - waiting {wait / 60:.0f} min to post at {sys.argv[1]} ET")
        time.sleep(wait)
    else:
        print(f"Slot time {sys.argv[1]} ET has passed - posting now")
