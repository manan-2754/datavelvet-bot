# 3D Explainer Bot — 4K step-by-step tech explainers, auto-posted 4×/day

Every run: **topic → Gemini storyboard → natural English narration with word timestamps → 4K (2160×3840) high-motion 3D diagram render, every animation fired on the exact word that describes it → YouTube Shorts + Instagram Reels**.

Runs on GitHub Actions 4 times a day (9am / 1pm / 5pm / 9pm Eastern), so your PC can be off. It stops posting after `RUN_UNTIL` (default 2027-02-08 = 4 months).

## Files

| File | What it does |
|---|---|
| `main.py` | Orchestrates one video (and uploads with `--post`) |
| `storyboard.py` | Gemini writes the scene-by-scene script + word-cued animation beats; validates it; topic queue in `state.json` |
| `motion3d.py` | 3D engine: lit 3D objects (servers, DBs, chips, devices…), moving camera, packets, flows, highlights, crashes, callouts, word-by-word captions → ffmpeg |
| `explainer_engine.py` | Text/drawing helpers used by motion3d (plus the earlier wireframe style) |
| `voice.py` | Human-sounding narration per scene + per-word timestamps (Microsoft neural voices via edge-tts) |
| `youtube_upload.py` | YouTube Data API upload (4K) |
| `instagram_upload.py` | Instagram Reels upload (direct file upload, 1080×1920 copy), token refresh |
| `explainer_topics.json` | 558 topics (~4.5 months at 4/day) |
| `storyboards/` | Hand-written storyboards — used as backup when Gemini is down |
| `.github/workflows/bot.yml` | The schedule |
| `legacy_main_v3.py`, `motion_graphics.py`, `notion_*` | Old v3 pipeline (no longer used) |

## Run locally

```bash
pip install -r requirements.txt
python main.py --preview                                   # 1080p test, ~2 min
python main.py                                             # full 4K from the next topic
python main.py --storyboard storyboards/dns_explained.json
```

## One-time setup for auto-posting

### YouTube
1. console.cloud.google.com → new project → enable **YouTube Data API v3**.
2. OAuth consent screen → External → add your Google account as a test user → **Publish app** (otherwise the login expires every 7 days).
3. Credentials → OAuth client ID → **Desktop app** → download as `client_secret.json` into this folder.
4. `python youtube_upload.py --auth` → log in and pick the channel. It prints the channel name and writes `token.json`.
5. **Important:** API projects that haven't passed Google's audit can only upload **private** videos.
   Request the (free) audit at support.google.com/youtube/contact/yt_api_form. Until it's approved, uploads land as private
   and you can flip them to public in YouTube Studio.

### Instagram
1. Make the account **Professional** (Creator or Business).
2. developers.facebook.com → Create app → add **Instagram** → *API setup with Instagram login* → add your account → generate a token
   with `instagram_business_basic` + `instagram_business_content_publish`.
3. Put it in `.env` as `IG_ACCESS_TOKEN=...` and run `python instagram_upload.py --whoami` → shows your username and id.

### GitHub (this is what makes it run while your PC is off)
1. Push this folder to a GitHub repo (**public** repos get unlimited free Actions minutes; one 4K render takes ~15–25 min,
   which is ~3,000 min/month — over the 2,000 free minutes for private repos).
2. Settings → Secrets and variables → Actions:
   - **Secrets:** `GEMINI_API_KEY`, `YT_TOKEN_JSON` (contents of token.json), `IG_ACCESS_TOKEN`, `IG_USER_ID`,
     `GH_PAT` (fine-grained token with *Secrets: read/write* on this repo — lets the bot save the refreshed Instagram token)
   - **Variables:** `AUTO_POST_YOUTUBE=true`, `AUTO_POST_INSTAGRAM=true`, `CHANNEL_HANDLE=@yourhandle`,
     optional `RUN_UNTIL=2027-02-08`, optional `YT_PRIVACY=private|unlisted|public`
3. Actions tab → enable workflows → "3D explainer - create + post" → **Run workflow** once to test.

Secrets are never committed: `.env`, `token.json`, `client_secret.json` are in `.gitignore`.

## Limits worth knowing
- YouTube API quota: 10,000 units/day, one upload = 1,600 → max 6 uploads/day (we do 4).
- Shorts must be ≤ 3 min; the bot refuses anything over 178 s (typical video: 100–140 s).
- YouTube/Instagram may limit reach or monetisation of fully automated, templated channels — check the stats after
  the first couple of weeks and vary topics/voices if needed.
