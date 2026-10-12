"""
Instagram Reels uploader (Instagram API with Instagram Login - no Facebook Page needed).

Instagram downloads the video from a public URL. In the GitHub Actions job the 1080x1920 copy is attached
to a release ("ig-media") in this repo, Instagram fetches it, and the asset is deleted after publishing.
The repo must be public so Instagram can reach the file. Instagram caps Reels at 1920px wide.

One-time setup:
  1. Switch your Instagram account to Professional (Creator or Business)
  2. developers.facebook.com -> Create app -> add "Instagram" product -> "API setup with Instagram login"
  3. Add your Instagram account as a tester / generate a token with instagram_business_basic +
     instagram_business_content_publish -> this is a long-lived token (60 days)
  4. GitHub secrets: IG_ACCESS_TOKEN, IG_USER_ID (python instagram_upload.py --whoami prints the id)
  The cloud job refreshes the token automatically (needs secret GH_PAT so it can save the new one).
"""
import os
from datetime import date, datetime, timedelta, timezone
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests

HOST = os.getenv("IG_GRAPH_HOST", "graph.instagram.com")
VERSION = os.getenv("IG_API_VERSION", "v23.0")


def _token():
    tok = os.getenv("IG_ACCESS_TOKEN", "").strip()
    if not tok:
        raise RuntimeError("IG_ACCESS_TOKEN is not set")
    return tok


def _user_id():
    uid = os.getenv("IG_USER_ID", "").strip()
    return uid or whoami()["id"]


def _check(r):
    if r.status_code >= 400:
        raise RuntimeError(f"Instagram API {r.status_code}: {r.text[:300]}")
    return r.json()


def whoami():
    return _check(requests.get(f"https://{HOST}/{VERSION}/me", params={"fields": "id,username", "access_token": _token()}, timeout=30))


def to_1080(video_path):
    from audio_build import ffmpeg as ffmpeg_exe
    out = Path(tempfile.gettempdir()) / f"ig_{Path(video_path).parent.name}.mp4"
    subprocess.run([ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(video_path), "-vf", "scale=1080:1920:flags=lanczos",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out)], check=True)
    return out


def _gh(method, url, **kw):
    headers = {"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}", "Accept": "application/vnd.github+json"}
    headers.update(kw.pop("headers", {}))
    r = requests.request(method, url, headers=headers, timeout=kw.pop("timeout", 60), **kw)
    if r.status_code >= 400 and r.status_code != 404:
        raise RuntimeError(f"GitHub API {r.status_code}: {r.text[:200]}")
    return r


def host_on_github(path, ctype="video/mp4"):
    """Attach the file to the 'ig-media' release of this repo and return (public_url, asset_api_url)."""
    repo = os.getenv("GITHUB_REPOSITORY")
    if not repo or not os.getenv("GITHUB_TOKEN"):
        raise RuntimeError("Instagram needs a public video URL - run inside GitHub Actions (GITHUB_TOKEN/GITHUB_REPOSITORY)")
    api = f"https://api.github.com/repos/{repo}/releases"
    r = _gh("GET", f"{api}/tags/ig-media")
    if r.status_code == 404:
        r = _gh("POST", api, json={"tag_name": "ig-media", "name": "Instagram media (temporary)",
                                   "body": "Temporary video files fetched by Instagram. Deleted after posting.",
                                   "prerelease": True})
    release = r.json()
    name = f"{int(time.time())}_{Path(path).name}"
    with open(path, "rb") as f:
        asset = _gh("POST", f"https://uploads.github.com/repos/{repo}/releases/{release['id']}/assets",
                    params={"name": name}, data=f, headers={"Content-Type": ctype}, timeout=600).json()
    return asset["browser_download_url"], asset["url"]


def upload_reel(video_path, caption, thumb_offset=None, cover=None):
    token, uid = _token(), _user_id()
    small = to_1080(video_path)
    url, asset_api = host_on_github(small)
    print(f"  Instagram: video hosted at {url}")
    cover_url, cover_api = host_on_github(cover, "image/jpeg") if cover else (None, None)
    try:
        fields = {"media_type": "REELS", "video_url": url, "caption": caption, "share_to_feed": "true",
                  **({"cover_url": cover_url} if cover_url else {"thumb_offset": str(int(thumb_offset))} if thumb_offset else {}),
                  "is_ai_generated": "true",   # Instagram's "AI info" self-disclosure label
                  "access_token": token}
        r = requests.post(f"https://{HOST}/{VERSION}/{uid}/media", data=fields, timeout=60)
        if r.status_code >= 400 and "is_ai_generated" in r.text:
            print(f"  ⚠️ Instagram rejected is_ai_generated ({r.text[:160]}) - posting with an AI note in the caption instead")
            fields.pop("is_ai_generated")
            fields["caption"] = caption + "\n\n(Made with AI)"
            r = requests.post(f"https://{HOST}/{VERSION}/{uid}/media", data=fields, timeout=60)
        container = _check(r)
        cid = container["id"]
        print("  Instagram: processing...")
        for _ in range(60):
            st = _check(requests.get(f"https://{HOST}/{VERSION}/{cid}",
                                     params={"fields": "status_code,status", "access_token": token}, timeout=30))
            if st.get("status_code") == "FINISHED":
                break
            if st.get("status_code") in ("ERROR", "EXPIRED"):
                raise RuntimeError(f"Instagram processing failed: {st}")
            time.sleep(10)
        else:
            raise RuntimeError("Instagram processing timed out")

        pub = _check(requests.post(f"https://{HOST}/{VERSION}/{uid}/media_publish",
                                   data={"creation_id": cid, "access_token": token}, timeout=60))
    finally:
        _gh("DELETE", asset_api)
        if cover_api:
            _gh("DELETE", cover_api)
        small.unlink(missing_ok=True)
    print(f"✅ Instagram: posted media {pub['id']}")
    return pub["id"]


def _wait(cid, token, tries=30):
    for _ in range(tries):
        st = _check(requests.get(f"https://{HOST}/{VERSION}/{cid}", params={"fields": "status_code", "access_token": token}, timeout=30))
        if st.get("status_code") in (None, "FINISHED"):
            return
        if st.get("status_code") in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram processing failed: {st}")
        time.sleep(5)


def upload_carousel(images, caption):
    """Posts a carousel (2-10 images) - a second, saveable post built from the video."""
    token, uid = _token(), _user_id()
    hosted = [host_on_github(p, "image/jpeg") for p in images[:10]]
    try:
        kids = []
        for url, _ in hosted:
            c = _check(requests.post(f"https://{HOST}/{VERSION}/{uid}/media", timeout=60,
                                     data={"image_url": url, "is_carousel_item": "true", "access_token": token}))
            kids.append(c["id"])
        for k in kids:
            _wait(k, token)
        box = _check(requests.post(f"https://{HOST}/{VERSION}/{uid}/media", timeout=60, data={
            "media_type": "CAROUSEL", "children": ",".join(kids), "caption": caption, "access_token": token}))
        _wait(box["id"], token)
        pub = _check(requests.post(f"https://{HOST}/{VERSION}/{uid}/media_publish", timeout=60,
                                   data={"creation_id": box["id"], "access_token": token}))
    finally:
        for _, api in hosted:
            _gh("DELETE", api)
    print(f"✅ Instagram: posted carousel {pub['id']}")
    return pub["id"]


def post_comment(media_id, text):
    """The account's first comment under a Reel (needs the instagram_business_manage_comments permission)."""
    if not (media_id and text):
        return None
    r = requests.post(f"https://{HOST}/v21.0/{media_id}/comments", params={"message": text[:300], "access_token": _token()}, timeout=30)
    if r.status_code != 200:
        print(f"  Instagram comment skipped: {r.status_code} {r.text[:120]}")
        return None
    print(f"  💬 Instagram comment posted: {text[:60]}")
    return r.json().get("id")


REFRESH_AFTER_DAYS = 55   # use the same token for 55 days, then refresh once (Instagram tokens last 60)


def refresh_token():
    """Extend the 60-day token once it is 55+ days old (daily refresh calls get flagged by Instagram).
    The last refresh date lives in the repo variable IG_TOKEN_REFRESHED; the new token goes back into the secret."""
    last = os.getenv("IG_TOKEN_REFRESHED", "").strip()
    if last:
        try:
            age = (datetime.now(timezone.utc).date() - date.fromisoformat(last[:10])).days
        except ValueError:
            age = REFRESH_AFTER_DAYS
        if age < REFRESH_AFTER_DAYS:
            print(f"Token is {age} days old - no Instagram call today; next refresh on day {REFRESH_AFTER_DAYS} "
                  f"({date.fromisoformat(last[:10]) + timedelta(days=REFRESH_AFTER_DAYS)})")
            return
        print(f"Token is {age} days old - refreshing (it expires on day 60)")
    old = _token()
    r = requests.get(f"https://{HOST}/refresh_access_token",
                     params={"grant_type": "ig_refresh_token", "access_token": old}, timeout=30)
    if r.status_code != 200:
        print(f"Token refresh FAILED: {r.status_code} {r.text[:200]}")
        sys.exit(1)                          # fail loudly: the workflow emails you, and retries tomorrow
    new = r.json()["access_token"]
    days = r.json().get("expires_in", 0) // 86400
    print(f"Instagram token refreshed - valid for {days} more days")
    if new != old and os.getenv("GH_PAT") and os.getenv("GITHUB_REPOSITORY"):
        print(f"::add-mask::{new}")
        repos = [os.environ["GITHUB_REPOSITORY"]] + [r.strip() for r in os.getenv("IG_TOKEN_REPOS", "").split(",") if r.strip()]
        for repo in dict.fromkeys(repos):   # every bot that posts to this Instagram account
            r2 = subprocess.run(["gh", "secret", "set", "IG_ACCESS_TOKEN", "--repo", repo, "--body", new],
                                env={**os.environ, "GH_TOKEN": os.environ["GH_PAT"]})
            print(f"Saved refreshed token to {repo}" if r2.returncode == 0 else f"Could not update {repo} (check GH_PAT repo access)")
    if os.getenv("GH_PAT") and os.getenv("GITHUB_REPOSITORY"):   # start the next 55-day count
        r3 = subprocess.run(["gh", "variable", "set", "IG_TOKEN_REFRESHED", "--repo", os.environ["GITHUB_REPOSITORY"],
                             "--body", datetime.now(timezone.utc).date().isoformat()], env={**os.environ, "GH_TOKEN": os.environ["GH_PAT"]})
        print("Saved the refresh date" if r3.returncode == 0 else "Could not save IG_TOKEN_REFRESHED (give GH_PAT 'Variables: write')")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env", override=True)
    if "--whoami" in sys.argv:
        print(whoami())
    elif "--refresh" in sys.argv:
        refresh_token()
    else:
        print(__doc__)
