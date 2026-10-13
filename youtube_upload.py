"""
YouTube Shorts uploader.

One-time setup on your PC (creates token.json, which holds a refresh token):
  1. console.cloud.google.com -> new project -> enable "YouTube Data API v3"
  2. OAuth consent screen -> External -> add yourself as a test user -> then click "Publish app"
     (apps left in "Testing" get refresh tokens that expire after 7 days)
  3. Credentials -> Create OAuth client ID -> Desktop app -> download JSON as client_secret.json here
  4. python youtube_upload.py --auth      (browser opens - pick the channel to post to)
  5. Put the contents of token.json in the GitHub secret YT_TOKEN_JSON
"""
import json
import os
import sys
import time
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

BASE = Path(__file__).parent
SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly"]
# asked for at --auth: also comments + playlists (force-ssl) and retention analytics. Runs use whatever the token has.
AUTH_SCOPES = SCOPES + ["https://www.googleapis.com/auth/youtube.force-ssl", "https://www.googleapis.com/auth/yt-analytics.readonly"]
TOKEN_FILE = BASE / "token.json"
CLIENT_SECRET = BASE / "client_secret.json"


def has_scope(creds, name):
    """True when the saved token includes this permission (e.g. 'force-ssl', 'yt-analytics')."""
    return any(name in s for s in (getattr(creds, "scopes", None) or []))


def get_credentials(interactive=False, fresh=False):
    creds = None
    if fresh:                                    # --auth: always ask again, with every permission the bot can use
        return _consent()
    env = os.getenv("YT_TOKEN_JSON", "").strip()
    if env:
        creds = Credentials.from_authorized_user_info(json.loads(env))
    elif TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE))
    if creds and not creds.valid and creds.refresh_token:
        creds.refresh(Request())
    if creds and creds.valid:
        return creds
    if not interactive:
        raise RuntimeError("No valid YouTube credentials - run `python youtube_upload.py --auth` once on your PC")
    return _consent()


def _consent():
    if not CLIENT_SECRET.exists():
        raise RuntimeError("client_secret.json not found - see the setup steps at the top of this file")
    from google_auth_oauthlib.flow import InstalledAppFlow
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), AUTH_SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")
    TOKEN_FILE.write_text(creds.to_json())
    return creds


def _api():
    return build("youtube", "v3", credentials=get_credentials(), cache_discovery=False)


def post_comment(video_id, text):
    """The channel's first comment under a video (a question that starts the replies). Pin it in the app if you like."""
    creds = get_credentials()
    if not (text and has_scope(creds, "force-ssl")):
        return None
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    r = yt.commentThreads().insert(part="snippet", body={"snippet": {"videoId": video_id,
                                   "topLevelComment": {"snippet": {"textOriginal": text[:500]}}}}).execute()
    print(f"  💬 YouTube comment posted: {text[:60]}")
    return r.get("id")


def add_to_playlist(video_id, title, description=""):
    """Adds the video to the channel's playlist with this title, creating the playlist the first time."""
    creds = get_credentials()
    if not (title and has_scope(creds, "force-ssl")):
        return None
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    pid, tok = None, None
    while not pid:
        res = yt.playlists().list(part="snippet", mine=True, maxResults=50, pageToken=tok).execute()
        pid = next((p["id"] for p in res.get("items", []) if p["snippet"]["title"] == title), None)
        tok = res.get("nextPageToken")
        if not tok:
            break
    if not pid:
        pid = yt.playlists().insert(part="snippet,status", body={"snippet": {"title": title, "description": description[:4900]},
                                                                  "status": {"privacyStatus": "public"}}).execute()["id"]
        print(f"  📂 created playlist: {title}")
    for k in range(5):                           # a brand-new playlist needs a few seconds before it accepts videos
        try:
            yt.playlistItems().insert(part="snippet", body={"snippet": {"playlistId": pid,
                                      "resourceId": {"kind": "youtube#video", "videoId": video_id}}}).execute()
            break
        except HttpError as e:
            if e.resp.status != 409 or k == 4:
                raise
            time.sleep(4 * (k + 1))
    print(f"  📂 added to playlist: {title}")
    return pid


def retention(video_ids, days=60):
    """Average % viewed, average view duration, subscribers gained and shares per video (YouTube Analytics)."""
    creds = get_credentials()
    if video_ids and not has_scope(creds, "yt-analytics"):
        print("  analytics: retention skipped - this YouTube login has no yt-analytics.readonly permission "
              "(re-run `python youtube_upload.py --auth` and update the YT_TOKEN_JSON secret)")
    if not (video_ids and has_scope(creds, "yt-analytics")):
        return {}
    from datetime import date, timedelta
    ya = build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)
    out = {}
    for i in range(0, len(video_ids), 200):
        ids = video_ids[i:i + 200]
        r = ya.reports().query(ids="channel==MINE", startDate=(date.today() - timedelta(days=days)).isoformat(),
                               endDate=date.today().isoformat(), dimensions="video", filters="video==" + ",".join(ids),
                               metrics="averageViewPercentage,averageViewDuration,subscribersGained,shares").execute()
        for row in r.get("rows", []):
            out[row[0]] = {"yt_avp": round(float(row[1]), 1), "yt_avd": round(float(row[2]), 1),
                           "yt_subs": int(row[3]), "yt_shares": int(row[4])}
    return out


def channel_name(youtube):
    items = youtube.channels().list(part="snippet", mine=True).execute().get("items", [])
    return items[0]["snippet"]["title"] if items else "(no channel)"


def upload_video(video_path, meta, privacy=None, thumbnail=None):
    youtube = build("youtube", "v3", credentials=get_credentials(), cache_discovery=False)
    body = {
        "snippet": {
            "title": meta["title"][:100],
            "description": meta.get("description", ""),
            "tags": meta.get("tags", []),
            "categoryId": "27",  # Education
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en",
        },
        "status": {
            "privacyStatus": privacy or os.getenv("YT_PRIVACY") or "public",
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": True,   # YouTube's "Altered or synthetic content" (AI) disclosure
        },
    }
    media = MediaFileUpload(str(video_path), mimetype="video/mp4", chunksize=16 * 1024 * 1024, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response, retries = None, 0
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                print(f"  YouTube upload {int(status.progress() * 100)}%")
        except HttpError as e:
            if e.resp.status in (500, 502, 503, 504) and retries < 5:
                retries += 1
                time.sleep(2 ** retries)
                continue
            raise
    vid = response["id"]
    if thumbnail:                           # custom thumbnails need a verified channel - skipped quietly otherwise
        try:
            youtube.thumbnails().set(videoId=vid, media_body=MediaFileUpload(str(thumbnail), mimetype="image/jpeg")).execute()
            print("  custom thumbnail set")
        except Exception as e:
            print(f"  custom thumbnail skipped ({str(e)[:120]})")
    print(f"✅ YouTube: https://youtube.com/{'shorts/' if '#shorts' in meta['title'].lower() else 'watch?v='}{vid}")
    return vid


if __name__ == "__main__":
    if "--auth" in sys.argv:
        creds = get_credentials(interactive=True, fresh=True)
        yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
        print(f"✅ Authorised for channel: {channel_name(yt)}")
        print(f"token saved to {TOKEN_FILE} - paste its contents into the GitHub secret YT_TOKEN_JSON")
    elif len(sys.argv) >= 2:
        folder = Path(sys.argv[1])
        upload_video(folder / "video.mp4", json.loads((folder / "meta.json").read_text(encoding="utf-8")))
    else:
        print(__doc__)
