<div align="center">

<img src="docs/logo.svg" alt="Pit Crew logo" width="120" />

# Pit Crew
### One vlog in. A week of Shorts and Reels out.

<p>
  <img src="https://img.shields.io/badge/Python-3.10+-3776ab?style=for-the-badge&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/Flask-3-000000?style=for-the-badge&logo=flask&logoColor=white" />
  <img src="https://img.shields.io/badge/faster--whisper-Speech_to_text-5a3fc0?style=for-the-badge" />
  <img src="https://img.shields.io/badge/FFmpeg-libass-007808?style=for-the-badge&logo=ffmpeg&logoColor=white" />
  <img src="https://img.shields.io/badge/Gemini-or_OpenAI-4285f4?style=for-the-badge&logo=googlegemini&logoColor=white" />
  <img src="https://img.shields.io/badge/YouTube-Data_API_v3-ff0000?style=for-the-badge&logo=youtube&logoColor=white" />
  <img src="https://img.shields.io/badge/Instagram-Graph_API-e1306c?style=for-the-badge&logo=instagram&logoColor=white" />
  <img src="https://img.shields.io/badge/SQLite-Accounts-003b57?style=for-the-badge&logo=sqlite&logoColor=white" />
</p>

**Pit Crew** turns one long vlog into finished vertical YouTube Shorts and Instagram Reels. It transcribes the vlog, finds the strongest stand-alone moments, cuts them to 9:16 around the creator's face, burns in word-by-word captions with an on-screen hook, designs a thumbnail for each, lets the creator play and approve them, then uploads and schedules them on YouTube and Instagram. It can also upload the whole vlog to YouTube with AI-written titles, a description with chapters, tags and a thumbnail.

> A creator films one long vlog a week. Cutting it into a week of Shorts takes hours. Pit Crew does the cutting, captions, thumbnails and posting; the creator just picks.

<p>
  <a href="docs/demo.mp4"><img src="docs/demo.gif" width="240" alt="Pit Crew demo: a creator's long edit turns into a stack of ready-to-post Shorts"></a>
  <br><sub>▶ <a href="docs/demo.mp4">Watch the demo video</a> (10 s)</sub>
</p>

[How it works](#how-it-works) · [Features](#features) · [Architecture](#system-architecture) · [Quick Start](#quick-start) · [Setup in detail](#setup-in-detail) · [Engineering decisions](#key-engineering-decisions)

*Formerly Clipline. The code folder and the GitHub repository are still called `clipline`.*

</div>

---

## What Makes This Different

Most clipping tools cut a video into pieces and stop there. Pit Crew carries each Short all the way to the creator's channels.

| Typical clipping tool | Pit Crew |
|---|---|
| Cuts at fixed lengths or loud moments | Reads the whole transcript (plus the vlog's own title and description) and picks moments that stand alone |
| Centre crop to 9:16 | Crop follows the creator's face |
| Generic captions | Word-by-word captions with a highlighted word and an opening hook in the creator's tone |
| Hooks that promise anything | Every hook must be true: a hook quoting a number the clip never says is dropped |
| Thumbnail = a random frame | The AI picks the best frame and writes two lines of text, in two looks you can switch |
| Download, then upload by hand | Uploads and schedules on YouTube, posts Reels to Instagram at their time |
| One account, one channel | Several YouTube channels and Instagram accounts per creator |
| "Views" with no context | Compares clips by their first 7 days, so new and old clips are judged fairly |

---

## How It Works

1. **Send the vlog.** Upload the file (sent in pieces, so a dropped connection carries on) or paste a Google Drive link. Optionally add the vlog's YouTube link, a note ("include the summit, skip the drive") and must-have moments by time.
2. **Transcribe.** faster-whisper writes down every word with exact timings. It uses an NVIDIA GPU when there is one, the processor otherwise.
3. **Find moments.** Gemini (or OpenAI) reads the full transcript and picks the strongest stand-alone moments, with a hook, title, thumbnail text and hashtags for each.
4. **Edit.** FFmpeg cuts each moment, crops to 9:16 around the face, burns in captions in the chosen style. Output is 1080×1920 at CRF 18.
5. **Thumbnails.** Gemini looks at 12 frames of each Short, picks one and writes a two-line text. Pit Crew crops it around the face and draws the text in one of two looks: **Frame** (colour-graded) or **Duotone** (a two-colour poster).
6. **Review.** Play every Short, edit titles and captions, pick a hook, **Try again** for a different moment, **Add a Short** for one the AI missed, or **Choose on the video** to mark start and end yourself.
7. **Post.** Upload and schedule on YouTube; plan Reels on Instagram on their own schedule. Pit Crew posts each Reel itself at its time.
8. **Learn.** Analytics shows each clip's first-week views per platform and what's working.

---

## Features

### Making Shorts
- **Moments that stand alone**, picked from the whole transcript, with the creator's note and must-have moments always included
- **Face-following 9:16 crop**, word-by-word captions (Bold, Boxed, Clean) and an opening hook banner, or no banner so the creator's own words open the Short
- **Hooks that are true**: three styles (Curiosity, Bold, Story) or the creator's own; any hook with a number not said in the clip is dropped
- **Thumbnails** in two switchable looks, with the thumbnail as the first frames of the upload so it can be picked as the Shorts-feed cover
- **Try again** on one Short, **Add a Short**, and **Choose on the video** for moments without talking

### Uploading a whole vlog
- AI title ideas, a description with chapters and hashtags, tags and a 16:9 thumbnail, all editable and saved as you type
- Public, scheduled, unlisted or private, then "Make Shorts & Reels from this vlog?" on the same video and transcript

### Posting
- **YouTube**: upload now, one or two a day, or a custom start and spacing; change time, edit and replace a scheduled Short
- **Instagram Reels**: their own schedule (or the same times as YouTube); Pit Crew posts them, since Instagram has no scheduling for apps
- **Several channels and accounts** per creator; whatever is already planned stays on its own channel

### Running it for many creators
- **A queue**: `JOB_SLOTS` vlogs at once, at most `JOB_SLOTS_PER_CREATOR` from one person; the rest show "Waiting for a free spot"
- **Uploads that survive**: 8 MB pieces, retries on a dropped connection, the same file carries on after the tab closes
- **Stop** while a vlog is being made, **Try again** after it stops (no second upload, the transcript is reused); vlogs under way at a restart start again by themselves
- **Emails** when Shorts are ready, a vlog stops, or posting fails, and never while the creator is watching the page
- **Limits**: longest vlog, monthly minutes per account, sign-ups per IP
- **Accounts**: email + password or Google, confirm your email, forgot password, delete account
- **Storage clean-up** on a timer: a vlog's video 72 h after the last edit, unposted drafts after 30 days, posted files 30 days after they went out (with a warning a day before)
- **Tokens encrypted** at rest; every creator-facing error is one plain sentence that says what to do next

### Analytics
- YouTube Shorts and Instagram Reels side by side: views, watch time, retention, traffic sources, audience
- **Your clips**: each Pit Crew clip's first-week views per platform, top clips and "What's working" (only when the difference is real)

---

## System Architecture

```
╔═══════════════════════════════════════════════════════════════════════════╗
║                         Pit Crew: one vlog's journey                      ║
╠═══════════════════════════════════════════════════════════════════════════╣
║                                                                           ║
║   Browser (any device)                                                    ║
║   ─────────────────────                                                   ║
║   Video file ──► 8 MB pieces (resumable) ──► /api/upload ──┐              ║
║   Google Drive link ───────────────────────────────────────┤              ║
║                                                             ▼             ║
║                                              ┌──────────────────────────┐ ║
║                                              │  Limits + "is it a video" │ ║
║                                              └────────────┬─────────────┘ ║
║                                                           ▼               ║
║   ┌─────────────────────────────────────────────────────────────────────┐ ║
║   │  QUEUE   JOB_SLOTS at once · JOB_SLOTS_PER_CREATOR per person        │ ║
║   │          recovered after a restart · Stop / Try again                │ ║
║   └───────────────────────────────┬─────────────────────────────────────┘ ║
║                                   ▼                                       ║
║   ┌─────────────────────────────────────────────────────────────────────┐ ║
║   │  PIPELINE  (pipeline/: no web code, becomes the cloud worker)        │ ║
║   │                                                                      │ ║
║   │  Transcribe ──► Find moments ──► Edit ──► Thumbnails                 │ ║
║   │  faster-whisper  Gemini/OpenAI   FFmpeg    Gemini picks the frame,   │ ║
║   │  (saved, reused) true hooks only face crop Pillow draws the look     │ ║
║   │                                  captions                            │ ║
║   └───────────────────────────────┬─────────────────────────────────────┘ ║
║                                   ▼                                       ║
║                     Review in the browser (edit, hooks,                   ║
║                     Try again, Add a Short, choose on video)              ║
║                                   │                                       ║
║                 ┌─────────────────┴─────────────────┐                     ║
║                 ▼                                   ▼                     ║
║        YouTube Data API v3                 Instagram scheduler            ║
║        upload + schedule now               posts each Reel at its time    ║
║        (thumbnail as first frames)         (Instagram fetches a signed,   ║
║                 │                           expiring video link)          ║
║                 └─────────────────┬─────────────────┘                     ║
║                                   ▼                                       ║
║                     Analytics: first-week views per clip                  ║
║                                                                           ║
║   Background: storage clean-up (15 min) · Reel numbers (daily) ·          ║
║               emails when away · YouTube Studio deletions synced          ║
╚═══════════════════════════════════════════════════════════════════════════╝
```

Today everything runs in **one process with threads**: the Flask server, the queue, the Instagram scheduler and the storage clean-up. Accounts live in SQLite (`data/clipline.db`) and each vlog in `jobs/<id>/job.json`. Pit Crew is moving to the cloud, so every change has to work the same on a Linux server as on a laptop (see [`CLAUDE.md`](CLAUDE.md)).

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Server** | Python 3.10+, Flask 3, plain threads (no Celery, no Redis) |
| **Transcription** | faster-whisper (batched, language voted across the whole video) |
| **Moments, hooks, titles** | Gemini (`google-genai`) or OpenAI, through one `ai_json()` with retries and model fallbacks |
| **Video** | FFmpeg with libass (captions), OpenCV (face finding), `imageio-ffmpeg` as a complete fallback FFmpeg |
| **Thumbnails** | Pillow, bundled OFL fonts (Anton, DM Serif Display) |
| **Posting** | YouTube Data API v3, YouTube Analytics API, Instagram API with Instagram Login |
| **Accounts** | SQLite, Werkzeug password hashing, signed session cookies, tokens encrypted with Fernet |
| **Page** | Plain HTML, CSS and JavaScript: no framework, no build step |

---

## Project Structure

```
clipline/
├── app.py                 # starts Pit Crew: loads .env, imports every web/ file, runs the server
├── settings.py            # ROOT and JOBS_DIR
├── pipeline/              # making Shorts (no web code: this becomes the cloud worker)
│   ├── transcribe.py      # faster-whisper, audio decoded by FFmpeg
│   ├── moments.py         # picking moments
│   ├── hooks.py           # hooks, with the "must be true" check
│   ├── reframe.py         # face-following 9:16 crop
│   ├── captions.py        # word-by-word captions (ASS)
│   ├── render.py          # FFmpeg render of one Short
│   ├── thumbnails/        # frames → plan (AI) → layout → looks/frame.py, looks/duotone.py
│   ├── vlog_meta.py       # titles, description with chapters, tags for a whole vlog
│   └── ai.py              # every AI call: Gemini or OpenAI, retries, fallbacks
├── youtube/               # Google sign-in, connecting YouTube, upload, schedule, analytics
├── instagram/             # connecting Instagram, posting Reels, Reel insights
├── accounts/              # accounts database, email, token encryption
├── web/                   # the web routes, one file per feature
│   ├── job_queue.py       # the vlog queue
│   ├── video_upload.py    # resumable uploads
│   ├── make_shorts.py     # one Shorts run
│   ├── posting.py         # YouTube upload and schedule
│   ├── instagram_posting.py  # Reel scheduler
│   ├── retention.py       # storage clean-up
│   └── ...                # one file per feature (see CLAUDE.md)
├── static/                # the page: index.html, sections/, css/, js/ (one file per screen or feature)
├── jobs/                  # everything Pit Crew makes, one folder per vlog (git-ignored)
├── data/                  # accounts database and secrets (git-ignored)
├── docs/                  # demo video, logo, the public home, privacy and terms pages
└── CLAUDE.md              # developer notes: where each feature lives, hard-won gotchas, how to test
```

---

## Quick Start

### Prerequisites

- Python 3.10 or newer
- FFmpeg and ffprobe on PATH
- A free Gemini API key (or an OpenAI key with credit)
- For posting: a free Google Cloud project (YouTube) and a Meta app (Instagram)

### Run it

```bash
git clone https://github.com/saumysoni/clipline.git
cd clipline
cp .env.example .env        # paste your key after GEMINI_API_KEY=
bash start-mac.command      # Windows: double-click start-windows.bat
```

The start script creates `.venv`, installs `requirements.txt`, downloads the speech model (about 500 MB, first run only) and opens **http://localhost:8000**. Create an account, then **+ Create → Make Shorts** with any vlog.

At this point you can make, play and download Shorts. Posting needs steps 5 and 6 below.

---

## Setup in detail

### 1. Install Python and FFmpeg

**Windows**
- Python 3.10 or newer from python.org. During install, tick **"Add python.exe to PATH"**.
- FFmpeg: open Command Prompt and run `winget install Gyan.FFmpeg`, then close and reopen Command Prompt.

**Mac**
- Install Homebrew from brew.sh if you don't have it, then in Terminal run: `brew install python ffmpeg`

Check it worked: `ffmpeg -version` should print a version number.

### 2. Get a free Gemini API key

Go to https://aistudio.google.com/apikey, sign in, and create a key.
In the `clipline` folder, copy `.env.example` to a new file named `.env` and paste the key after `GEMINI_API_KEY=`.
(On a Mac, in Terminal: `cp .env.example .env`, then `open -e .env` to edit it.) Never commit `.env`; it's your private key.

**Prefer OpenAI?** Set `AI_PROVIDER=openai` and paste an OpenAI key after `OPENAI_API_KEY=` instead
(from https://platform.openai.com/api-keys; OpenAI's API is paid, so the account needs credit).
`OPENAI_MODEL` picks the model. Everything else works the same.

### 2b. Let Pit Crew read your vlog's YouTube title and description (optional)

On the start page you can paste the vlog's YouTube link and Pit Crew fills in its title and description,
which helps it pick better moments and write titles that sound like you. Without this step it still
fills in the title; for the description too:

1. In https://console.cloud.google.com, create a project (or use the one from step 5).
2. **APIs & Services → Library**: enable **YouTube Data API v3**.
3. **Credentials → Create credentials → API key**. Click the key, and under **API restrictions** choose
   *Restrict key* → *YouTube Data API v3*.
4. Paste it after `YOUTUBE_API_KEY=` in `.env` and restart Pit Crew.

Pit Crew only reads the public text. It never downloads the video from YouTube (YouTube's rules don't
allow apps to do that), so you still add the original video file.

### 3. Add a caption font (optional, recommended)

Download **Montserrat** from Google Fonts and put `Montserrat-ExtraBold.ttf` in the `fonts` folder. Any bold font works; if you use another, change `CAPTION_FONT` in `.env` to its name.

### 4. Start Pit Crew

- **Windows:** double-click `start-windows.bat`
- **Mac:** double-click `start-mac.command` (first time: right-click, Open)

The first run installs everything and downloads the speech model (around 500 MB) so give it a few minutes. Your browser then opens **http://localhost:8000**. Keep the black window open while you use it.

**Accounts.** The first screen asks you to sign in. Create an account with your email and a password (at least
8 characters), or use **Continue with Google** once step 5 is done. Each account sees only its own vlogs, Shorts
and YouTube channel. A new email account gets a link to confirm the email, so Pit Crew can email you when Shorts
are ready. **Forgot password?** emails a reset link. Until step 7 is done, both links are printed in the Terminal window.

### 5. Turn on Google sign-in and automatic YouTube posting

1. Go to https://console.cloud.google.com and create a project (free, no card needed).
2. **APIs & Services → Library**: search **YouTube Data API v3** and click **Enable**. Do the same for **YouTube Analytics API** (for the Analytics page).
3. **OAuth consent screen**: choose **External**, fill in the app name and your email. Under **Test users**, add the Gmail address of the creator's YouTube channel.
4. **Credentials → Create credentials → OAuth client ID → Web application**. Under **Authorised redirect URIs** add `http://localhost:8000/api/youtube/callback`. Download the JSON file and put it in the app's folder (Google's long file name `client_secret_….json` works as it is). On a server, put `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in `.env` instead. (An older **Desktop app** client may also work; if Google says `redirect_uri_mismatch`, make a Web application client as above.)
5. **Let anyone sign in: publish the app.** On the OAuth consent screen (newer consoles: **Google Auth Platform → Audience**), click **Publish app** so the status is **In production**. While it's in **Testing**, Google only lets in the Gmail addresses listed under Test users, even for Continue with Google. Publishing doesn't start a review.
   - **Continue with Google** only asks for name and email, so anyone can use it with no warning and no limit.
   - **Connect YouTube** asks to manage the creator's videos, a "sensitive" permission. Until Google verifies Pit Crew, people see a "Google hasn't verified this app" screen (they click **Advanced → Go to Pit Crew**), and at most **100 people** in total can connect a channel. To lift both, apply for verification under **Verification Center**: you need a home page on your own domain, a privacy policy, and a short video showing why Pit Crew needs YouTube access.
6. Restart Pit Crew. The badge in the sidebar should say "Connect YouTube".

**Connect YouTube, then post.** Click **Connect YouTube** on the start page (or the sidebar badge). If you skip it, **Upload to YouTube** (on the **Post** page you reach with **Next: post** after reviewing) asks you to connect first. A small Google window opens: choose the channel's account, leave every box ticked, and click Allow. The window closes and Pit Crew shows "Posting to *your channel*". The connection is saved with your Pit Crew account, so you only connect once. The YouTube account can be a different Google account from the one you sign in to Pit Crew with.

**Thumbnails and links on Shorts.** Each Short's description links the full vlog and @mentions the channel (YouTube only lets the @mention be tapped on Shorts). Pit Crew sets the thumbnail through YouTube for search, the home page and subscriptions (this needs a phone-verified channel, which takes a minute at youtube.com/verify) and puts it in as the first frames of each Short (a fifth of a second). YouTube doesn't let apps set the Shorts-feed picture or the tappable **Related video**, so the Posted page lists two quick Studio steps per Short, with **Download thumbnail** next to **Open in Studio**.

Then tick the Shorts you want and choose when they go out:
- **One a day / two a day**: starting tomorrow, at 12 PM and/or 6 PM your time.
- **Starting on a day and time I choose**: pick the first Short's date and time, and how far apart the rest are.
- **All at once, right away**: posts them now (privacy set by `POST_NOW_PRIVACY` in `.env`).

If posting stops halfway (no internet, YouTube's daily limit), press the button again: Shorts already on YouTube are marked "On YouTube" and are never posted twice.

**Your scheduled Shorts.** **Scheduled** in the sidebar (which also lists Reels planned for Instagram) lists every Short Pit Crew has uploaded, with its live status on YouTube:
- **Change time** moves a scheduled Short to another date and time.
- **Edit Short** opens it on its review screen. Change the title, hook or moment there, then press **Update on YouTube**. A new title is just changed on YouTube. A changed video is uploaded again with the same time and the old upload is deleted, so the link to the Short changes. Pit Crew won't replace a Short that's already public (it would lose its views and comments).
- A Short Pit Crew can't find on your channel (deleted in YouTube Studio?) shows **Not found on YouTube**. Click **Unmark it** to upload it again. Shorts on another channel are left alone.

Open Pit Crew at `http://localhost:8000`, the address it opens by itself. Google only sends you back to the exact address registered in step 4, so `http://127.0.0.1:8000` won't work for Google sign-in. Continue with Google and Connect YouTube both use that one address. When Pit Crew runs on a server, register that server's address instead (for example `https://pitcrew.example.com/api/youtube/callback`), set `YOUTUBE_REDIRECT_URI` to the same address, and set `SECRET_KEY`, `DATABASE_PATH` and `SESSION_COOKIE_SECURE=1` in `.env`.

**Analytics.** **Analytics** in the sidebar shows how every Short on your channel is doing: views, watch time, likes, comments, shares, subscribers, a views-per-day chart, top Shorts (click one for its retention curve), how viewers find you, countries, age and gender, plus Instagram Reels once Instagram is connected. If you connected YouTube before Analytics existed, click **Connect again** there once so Pit Crew can read YouTube Analytics.

**Things to know about posting**
- **Uploads stay private until your project passes YouTube's API audit.** This is YouTube's rule for new projects. During a trial, open each upload in YouTube Studio and set it to public or scheduled there (Pit Crew shows an "Open in Studio" link for each one). To lift the limit, apply for the free audit from the YouTube API Services page; you'll need a short privacy policy and a description of the app.
- While the app is in **Testing** mode, a YouTube connection expires after about a week; just connect again when asked. Publishing the app (step 5.5) ends that.
- Each account's YouTube connections are stored encrypted in `data/clipline.db` (the key is `TOKEN_KEY`, else `data/token_key`: back it up, or everyone has to connect again). Keep the `data` folder private (it's git-ignored). **Disconnect** removes one channel and withdraws the permission at Google.
- **Several channels or Instagram accounts.** Click the YouTube or Instagram button under **Channels** in the sidebar: **Add channel** / **Add account** connects another one, and clicking a connected one switches to it straight away (no new sign-in). New Shorts and Reels go to the one that's ticked, and Analytics shows it. Shorts already posted or scheduled stay on their own channel, and changing them later (new time, Replace) goes to that channel. Connections stay until you disconnect them; signing out of Pit Crew doesn't remove them, so planned Reels still go out.
  - While the Google app is in **Testing**, every Google account you connect must be on the OAuth consent screen's **Test users** list. Channels that belong to the same Google account (brand channels) need nothing extra: Google asks which channel when you connect.
  - Each extra Instagram account must be added as an **Instagram tester** and accept the invite (step 6.4). **Add account** makes Instagram ask which account to log in as.
- Pit Crew asks to **manage your YouTube videos**, which it needs to show your channel's name, change a scheduled time and replace an edited Short. It only ever touches the Shorts it uploaded. An old `token.json` from earlier versions isn't used any more and can be deleted.
- Custom Shorts thumbnails are rolling out to YouTube Partner Program channels first (since July 2026), and need a phone-verified channel. On other channels YouTube may refuse them. If YouTube refuses, Pit Crew still uploads the Short and tells you to add the thumbnail in Studio (the file is in the `jobs` folder).

### 6. Post to Instagram too (optional)

Pit Crew posts Reels with the **Instagram API with Instagram Login**: the creator signs in with Instagram itself (no Facebook Page needed).

1. **Make the Instagram account professional** (Business or Creator, free). In the Instagram app: **Profile › ☰ › Settings › Account type and tools › Switch to professional account**. Followers and posts stay. Pit Crew checks this when you connect and shows these steps if needed.
2. **Create the Meta app.** Go to https://developers.facebook.com/apps (log in with Facebook; register as a developer if asked), click **Create app**, give it a name (e.g. Pit Crew), choose the use case **Manage messaging & content on Instagram**, and skip connecting a business portfolio.
3. **Get the Instagram keys.** In the app: **Instagram → API setup with Instagram login**. Copy the **Instagram app ID** and **Instagram app secret** (not the Facebook App ID at the top) into `.env`:
   ```
   INSTAGRAM_APP_ID=...
   INSTAGRAM_APP_SECRET=...
   ```
4. **Add yourself as a tester.** **App roles → Roles → Instagram testers → Add people**, type the Instagram username. Then accept it in the Instagram app: **Settings › Website permissions › Apps and websites › Tester invites** (on the web: instagram.com › Settings › Apps and websites). Until Meta reviews the app, only testers can connect.
5. **Add the redirect address.** In **API setup with Instagram login → 3. Set up Instagram business login → Business login settings → OAuth redirect URIs**, add `http://localhost:8000/api/instagram/callback` and save.
   - **If Meta refuses it** (it may accept only `https://` addresses), give your computer a temporary https address with a free tunnel. Install it once with `brew install cloudflared` (Windows: `winget install Cloudflare.cloudflared`). With Pit Crew running, open a second Terminal window and run `cloudflared tunnel --url http://localhost:8000`. It prints an address like `https://random-words.trycloudflare.com`. Add `https://random-words.trycloudflare.com/api/instagram/callback` as the redirect URI on Meta, put the same address in `.env` as `INSTAGRAM_REDIRECT_URI=...`, and restart Pit Crew. Keep using `http://localhost:8000` as usual; only Instagram's reply goes through the tunnel.
   - The tunnel is only needed while you click **Connect Instagram**; close it afterwards. The connection lasts 60 days and Pit Crew renews it on its own whenever it runs. The tunnel address changes every time you start it, so if you connect again later, update both places.
6. **Restart Pit Crew**, open the **Post** page (or click **Connect Instagram** in the sidebar), and connect. The sidebar badge then shows your @username.

**Posting Reels.** Each Short gets its own Instagram schedule: **Same times as YouTube**, the same presets, a custom start and spacing, or right away. Instagram doesn't let apps schedule posts, so Pit Crew posts each Reel itself at its time: keep Pit Crew running (Reels that came due while it was closed go out when it starts again). Instagram downloads each Reel from Pit Crew, so Pit Crew must be reachable over https when a Reel goes out: on a server that's automatic (set `PUBLIC_URL` to its address); on your computer, keep the tunnel from step 5 running. Each Short's card has an **Instagram** tab with its caption (suggested from the title and the full video's name on YouTube; edit it freely) and the **Hashtags** shared with YouTube; the Short's thumbnail frame becomes the Reel cover. Instagram allows 100 posts by app per account per day. If posting stops, the Reel shows **Try again**; if Pit Crew was closed in the middle of posting, check Instagram first so nothing is posted twice.

### 7. Send emails (optional)

Pit Crew emails password reset links, the link to confirm a new account's email, and notices when a creator is away: Shorts ready, a vlog stopped, posting failed, and a day before a video or draft is deleted. Until email is set up, nothing is sent and each email is printed in the Terminal window instead, which is fine on your own computer.

To send real emails from a Gmail account:
1. Turn on 2-Step Verification for the Google account (https://myaccount.google.com/security).
2. Make an **app password** at https://myaccount.google.com/apppasswords (name it Pit Crew) and copy the 16 letters.
3. Add to `.env`, then restart Pit Crew:
   ```
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=you@gmail.com
   SMTP_PASSWORD=the16letterapppassword
   ```

Any other email service with SMTP works the same way (put its host, port, user and password instead). For real users, send from your own domain with SPF and DKIM set up, or emails land in spam. On a server, also set `APP_URL` to Pit Crew's public address so the links in emails point to the right place. Set `SUPPORT_EMAIL` to show a **Help** link in the sidebar and **Get help** (with a reference) on a vlog that stopped.

**Signing in with Google when you made your account with a password:** Pit Crew shows "Email already exists" in red and doesn't join the two. Sign in with your email and password (or use Forgot password).

### Several vlogs at once, and big files

Pit Crew makes `JOB_SLOTS` vlogs at a time (2), at most `JOB_SLOTS_PER_CREATOR` (1) from one person; the others show
**Waiting for a free spot** (or **Starts after your other vlog**) and start by themselves. If Pit Crew is closed or
restarted while vlogs are being made, they start again by themselves the next time (a vlog that stopped Pit Crew twice
stays stopped, with Try again). Videos are sent in pieces: if the connection drops, Pit Crew keeps trying, and if the
tab closes, choosing the same file again carries on where it stopped. Files over `MAX_UPLOAD_GB` (30) are refused.

Vlogs can be up to 3 hours long (`MAX_VLOG_MINUTES`); `MONTHLY_VLOG_MINUTES` limits how many minutes of vlogs one
account can have made each month (none by default). Settings shows how much is used.

### Storage: what Pit Crew deletes, and when

To keep storage free, Pit Crew deletes:
- **a vlog's video 72 hours after you last edited it** (any change to one of its Shorts restarts the clock). Its Shorts, thumbnails, transcript and posts stay; Try again, hooks and new Shorts then need the vlog uploaded again (the same file skips transcribing);
- **a vlog that stopped, 72 hours after it stopped** (its video; the whole vlog if it made nothing to keep);
- **Shorts you never posted, 30 days after you last edited them;**
- **a posted Short's video file 30 days after it went out** (download it from YouTube Studio after that; its record and numbers stay).

A day before a video or draft goes, its card says so and you get an email (step 7). Change the times in `.env` (`KEEP_ORIGINAL_HOURS`, `KEEP_DRAFT_DAYS`, `KEEP_POSTED_DAYS`); `0` keeps forever. **Delete video** on the Vlogs page deletes a vlog's video straight away; tick several (or **Select all**) to delete them together.

### Running it on a server

Set these in the server's environment (all are documented in `.env.example`):

| Setting | Why |
|---|---|
| `APP_URL`, `PUBLIC_URL` | Links in emails; the https address Instagram downloads Reels from |
| `SECRET_KEY`, `SESSION_COOKIE_SECURE=1` | Signs sign-in cookies; sends them only over https |
| `TOKEN_KEY` | Encrypts saved YouTube/Instagram tokens. Keep it in the secret manager and back it up |
| `TRUST_PROXY=1` | Sees each visitor's real address behind a load balancer (sign-in and sign-up limits) |
| `YOUTUBE_REDIRECT_URI`, `INSTAGRAM_REDIRECT_URI`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Sign-in redirects on the server's address |
| `JOB_SLOTS`, `WHISPER_THREADS`, `WHISPER_DEVICE` | How much runs at once; `JOB_SLOTS × WHISPER_THREADS` ≈ the number of cores |
| `MONTHLY_VLOG_MINUTES`, `MAX_VLOG_MINUTES`, `MAX_UPLOAD_GB` | Limits per creator |
| `SUPPORT_EMAIL` | Where creators write for help |
| `DATABASE_PATH`, `JOBS_DIR` | Lasting storage for accounts and vlogs |

Run **one** Pit Crew process with threads (no gunicorn `--preload`): the queue, the uploads and the Instagram scheduler live in that process. Any proxy in front must accept request bodies of at least 8 MB.

---

## Running Tests

There is no automated test suite yet. [`CLAUDE.md`](CLAUDE.md) explains how to test without using up Gemini or YouTube quota: a 90-second test clip, a fake Gemini client, faster encoder settings, and how to check the output frame by frame. Tests must set `DATABASE_PATH` and `JOBS_DIR` to temporary paths before importing `app`.

---

## Key Engineering Decisions

**1. Never download from YouTube.**
YouTube's API rules forbid apps from downloading or storing YouTube videos, even the creator's own, and breaking that risks the API access posting depends on. Pit Crew reads only the public text of a YouTube link. The video always comes from an upload or a Drive link.

**2. Hooks must be true.**
An on-screen hook that promises something the clip doesn't deliver costs the creator trust. Every prompt carries the same rule (no invented facts), and any hook quoting a number that isn't said in the moment is dropped before the creator sees it.

**3. Audio decoded by FFmpeg, language voted across the whole video.**
faster-whisper's own decoder broke on a library update, so FFmpeg pipes raw audio in. Batched transcription guessed an English vlog with car noise as Welsh, so the language is voted over 8 clips spread through the video (and Pit Crew transcribes as English by default).

**4. The thumbnail goes in as the first frames.**
YouTube's API can't set the Shorts-feed picture. Pit Crew joins the thumbnail onto the start of the upload (a fifth of a second, without re-encoding the Short), so the creator can pick it as the cover in the YouTube app.

**5. Instagram downloads the Reel from Pit Crew.**
With Instagram Login, Instagram only accepts a `video_url`. Pit Crew serves each Reel from a signed link that expires, and posts at the planned time itself, because Instagram has no scheduling for apps.

**6. Compare clips by their first 7 days.**
Lifetime totals favour old clips. YouTube clips are compared by their first-week views; Instagram only gives running totals, so Pit Crew saves each Reel's numbers daily and reads day 7. "What's working" only speaks up when a difference is real.

**7. One queue, and nothing is lost on a restart.**
Each vlog runs transcription and FFmpeg, so a handful at once could run a server out of memory. Every run goes through one queue with a per-creator limit, a restart picks running vlogs up again (at most twice, so one bad video can't crash the server in a loop), and Stop / Try again reuse the saved video and transcript.

**8. Plain words for creators.**
The people using Pit Crew are creators, not developers. Every error they can see is one plain sentence that says what to do next. Setup problems (a missing key, a retired AI model) are written to the server log and shown to creators as "isn't available right now".

---

## What Pit Crew Does and Never Does

| Pit Crew does | Pit Crew never does |
|---|---|
| Suggest moments, hooks, titles and thumbnails | Post anything the creator didn't tick and schedule |
| Upload to the channels the creator connected | Touch videos it didn't upload |
| Post Reels at the time the creator chose | Re-post a Reel that may already have gone out (it asks the creator to check) |
| Read a vlog's public YouTube title and description | Download a video from YouTube |
| Keep the creator's files for a set time, then clean up | Keep tokens in readable form |
| Write hooks from what's said in the clip | Invent facts or numbers in a hook |

---

## Future Scope

- **Cloud hosting.** The queue, uploads and Instagram scheduler become a real job queue with workers and direct-to-storage uploads; `jobs/` moves to file storage and SQLite to a database server.
- **More languages.** Pit Crew is English-only today. Hindi and Hinglish were tried and dropped; they need a better transcription model.
- **Plans and billing** on top of the monthly allowance.
- **An admin view** for support: users, stopped vlogs and their error details, the queue.
- **Automated tests**, starting with moment cleaning, caption timing and schedule planning.
- **More platforms**, such as TikTok, once their posting APIs allow it.

---

## If something goes wrong

| Message | Fix |
|---|---|
| "Pit Crew's AI isn't available right now" | Check the terminal: the key is missing or refused (`GEMINI_API_KEY` / `OPENAI_API_KEY`), or no current model is available (`GEMINI_MODEL`). |
| "Pit Crew's video editor isn't working right now" | FFmpeg isn't installed or not on PATH (step 1). Reopen the window after installing. |
| Drive link fails | Set sharing to "Anyone with the link", or upload the file instead. |
| Captions use a plain font | Put the font file in `fonts` and make `CAPTION_FONT` match its name. |
| The AI service was too busy | Google's servers are busy. Pit Crew retries and tries other models by itself; if it still fails, press **Try again** in a few minutes. The transcript is saved. |
| The AI has reached its limit for now | Wait a while and press **Try again**; the transcript is reused. |
| `No option name near 'captions_1.ass...'` | Your FFmpeg was installed without caption support. Pit Crew switches to a complete FFmpeg add-on by itself; restart with the start script so it gets installed. |
| Your OpenAI account has no credit left | Add credit on OpenAI's billing page and try again. |
| Upload says quota exceeded | YouTube's daily quota is used up. Try again tomorrow. |
| Google says `redirect_uri_mismatch` when signing in | The address isn't registered on your OAuth client. Follow step 5.4 exactly, and open Pit Crew at `http://localhost:8000`. |
| Google says "access blocked" | The app is still in Testing. Publish it (step 5.5), or add that Gmail address under **Test users**. |
| "Google hasn't verified this app" when connecting YouTube | Expected until Google verifies Pit Crew (step 5.5). Click **Advanced → Go to Pit Crew**. |
| YouTube/Instagram show "Connect" after moving the database | The tokens are encrypted with `data/token_key` (or `TOKEN_KEY`). Bring the key with the database, or connect again. |

---

## Tips for the best Shorts

- **Use the original export**, not a video downloaded from YouTube. 4K sources give the sharpest vertical crops; a 1080p source works but is softer once cropped.
- Videos where the creator talks to camera give the best results, because both the moment-picking and the face-centred crop rely on speech and a visible face.
- Pit Crew is made for English vlogs for now. Vlogs in other languages, or mixing Hindi and English, don't come out well yet.
- A 45-minute vlog takes roughly 5–20 minutes on a typical laptop, mostly transcription and editing. On a computer with an NVIDIA graphics card, transcription uses it automatically. The transcript is saved, so it's never transcribed twice for the same vlog.

---

## Working on the code

Start with [`CLAUDE.md`](CLAUDE.md). It explains where each feature lives (one feature per file, so two people can work without touching the same file), the problems already solved and why, and how to test without using up Gemini or YouTube quota. Each person has one branch (Saumya `saumya`, Nesh `nesh`; no other branches) and changes reach `main` only through a pull request:

```bash
git checkout saumya                # or nesh
git fetch origin && git merge origin/main   # level with main first
# ...edit, then try it with: bash start-mac.command
git add -A && git commit -m "Describe the change"
git push                           # then open the pull request (saumya -> main) on GitHub
```

<div align="center">

<sub>Python · Flask · faster-whisper · FFmpeg · OpenCV · Pillow · Gemini · OpenAI · YouTube Data API · Instagram API · SQLite</sub>

</div>
