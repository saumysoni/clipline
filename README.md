# Clipline

Turn one long vlog into finished YouTube Shorts: it finds the best moments, cuts them vertical around the creator's face, burns in word-by-word captions with an on-screen hook, makes a thumbnail for each, lets you play and approve them, then uploads and schedules them on the channel.

Everything runs on your own computer with free tools. The only accounts you need are a free Gemini API key (or an OpenAI key) and (for auto-posting) a free Google Cloud project.

<p align="center">
  <a href="docs/demo.mp4"><img src="docs/demo.gif" width="240" alt="Clipline demo: a creator's long edit turns into a stack of ready-to-post Shorts"></a>
  <br><sub>▶ <a href="docs/demo.mp4">Watch the demo video</a> (10 s)</sub>
</p>

## What happens when you click "Make my Shorts"

1. **Transcribe.** faster-whisper (open-source Whisper) writes down every word with exact timings. Runs on your computer.
2. **Find moments.** Gemini reads the full transcript (plus the vlog's title and description, if you give them) and picks the strongest stand-alone moments, with a hook, title, thumbnail text and hashtags for each, written in the creator's tone.
3. **Edit.** FFmpeg cuts each moment, crops to 9:16 centred on the face, and burns in captions in the style you chose. Output is 1080×1920, high quality (CRF 18).
4. **Thumbnails.** Gemini (always Gemini, even when OpenAI picks the moments) looks at frames from each Short, picks the best moment (sharp, a strong reaction, or the thing the Short is about) and writes a short two-line text. Clipline crops it to the Shorts shape around the face and adds the text in the style creators use. Each Short has two looks you can switch between on its card in Review: **Frame** (the moment itself, colour-graded, the default) and **Duotone** (a two-colour poster in that Short's own colour). The download button next to them saves the thumbnail.
5. **Review.** You play every Short in the browser, edit titles, untick any you don't want. Not happy with one? **Try again** picks a different moment (optionally from your description or exact times). **Add a Short** makes one from a moment the AI missed. Under **Hook**, choose between three opening texts (Curiosity, Bold, Story), type your own, ask for new ones, or turn the text off so your own words open the Short. In both, **Choose on the video** lets you play through the vlog and mark the start and end yourself, which is the way to get scenes without talking (the AI only knows what's said).

Before you start, you can also tell Clipline what you want ("include the summit, skip the drive") and add **must-have moments** by their times; those always become Shorts and the AI picks the rest.
6. **Post.** The approved Shorts are uploaded to YouTube and scheduled.

All files are saved in the `jobs` folder, so you can also download and post them by hand.

---

## Setup (about 20 minutes, once)

### 0. Get the code

```bash
git clone https://github.com/saumysoni/clipline.git
cd clipline
```

(Or click **Code → Download ZIP** on GitHub and unzip it.)

### 1. Install Python and FFmpeg

**Windows**
- Python 3.10 or newer from python.org. During install, tick **"Add python.exe to PATH"**.
- FFmpeg: open Command Prompt and run `winget install Gyan.FFmpeg`, then close and reopen Command Prompt.

**Mac**
- Install Homebrew from brew.sh if you don't have it, then in Terminal run: `brew install python ffmpeg`

Check it worked: `ffmpeg -version` should print a version number.

### 2. Get a free Gemini API key

Go to https://aistudio.google.com/apikey, sign in, and create a key.
In the Clipline folder, copy `.env.example` to a new file named `.env` and paste the key after `GEMINI_API_KEY=`.
(On a Mac, in Terminal: `cp .env.example .env`, then `open -e .env` to edit it.) Never commit `.env`; it's your private key.

**Prefer OpenAI?** Set `AI_PROVIDER=openai` and paste an OpenAI key after `OPENAI_API_KEY=` instead
(from https://platform.openai.com/api-keys; OpenAI's API is paid, so the account needs credit).
`OPENAI_MODEL` picks the model. Everything else works the same.

### 2b. Let Clipline read your vlog's YouTube title and description (optional)

On the start page you can paste the vlog's YouTube link and Clipline fills in its title and description,
which helps it pick better moments and write titles that sound like you. Without this step it still
fills in the title; for the description too:

1. In https://console.cloud.google.com, create a project (or use the one from step 5).
2. **APIs & Services → Library**: enable **YouTube Data API v3**.
3. **Credentials → Create credentials → API key**. Click the key, and under **API restrictions** choose
   *Restrict key* → *YouTube Data API v3*.
4. Paste it after `YOUTUBE_API_KEY=` in `.env` and restart Clipline.

Clipline only reads the public text. It never downloads the video from YouTube (YouTube's rules don't
allow apps to do that), so you still add the original video file.

### 3. Add a caption font (optional, recommended)

Download **Montserrat** from Google Fonts and put `Montserrat-ExtraBold.ttf` in the `fonts` folder. Any bold font works; if you use another, change `CAPTION_FONT` in `.env` to its name.

### 4. Start Clipline

- **Windows:** double-click `start-windows.bat`
- **Mac:** double-click `start-mac.command` (first time: right-click, Open)

The first run installs everything and downloads the speech model (around 500 MB) so give it a few minutes. Your browser then opens **http://localhost:8000**. Keep the black window open while you use it.

At this point you can already make, play, and download Shorts. Step 5 only adds automatic posting.

**Accounts.** The first screen asks you to sign in. Create an account with your email and a password (at least
8 characters), or use **Continue with Google** once step 5 is done. Each account sees only its own vlogs, Shorts
and YouTube channel. Vlogs made before Clipline had accounts belong to the first account created. There's no
"forgot password" yet (it needs email sending); someone who signed up with Google can always use Google.

### 5. Turn on Google sign-in and automatic YouTube posting

1. Go to https://console.cloud.google.com and create a project (free, no card needed).
2. **APIs & Services → Library**: search **YouTube Data API v3** and click **Enable**.
3. **OAuth consent screen**: choose **External**, fill in the app name and your email. Under **Test users**, add the Gmail address of the creator's YouTube channel.
4. **Credentials → Create credentials → OAuth client ID → Web application**. Under **Authorised redirect URIs** add `http://localhost:8000/api/youtube/callback`. Download the JSON file and put it in the Clipline folder (Google's long file name `client_secret_….json` works as it is). On a server, put `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in `.env` instead. (An older **Desktop app** client may also work; if Google says `redirect_uri_mismatch`, make a Web application client as above.)
5. **Let anyone sign in: publish the app.** On the OAuth consent screen (newer consoles: **Google Auth Platform → Audience**), click **Publish app** so the status is **In production**. While it's in **Testing**, Google only lets in the Gmail addresses listed under Test users, even for Continue with Google. Publishing doesn't start a review.
   - **Continue with Google** only asks for name and email, so anyone can use it with no warning and no limit.
   - **Connect YouTube** asks to manage the creator's videos, a "sensitive" permission. Until Google verifies Clipline, people see a "Google hasn't verified this app" screen (they click **Advanced → Go to Clipline**), and at most **100 people** in total can connect a channel. To lift both, apply for verification under **Verification Center**: you need a home page on your own domain, a privacy policy, and a short video showing why Clipline needs YouTube access.
6. Restart Clipline. The badge in the sidebar should say "Connect YouTube".

**Connect YouTube, then post.** Click **Connect YouTube** on the start page (or the sidebar badge). If you skip it, **Upload to YouTube** (on the **Post** page you reach with **Next: post** after reviewing) asks you to connect first. (**Upload to Instagram** is shown but not available yet.) A small Google window opens: choose the channel's account, leave every box ticked, and click Allow. The window closes and Clipline shows "Posting to *your channel*". The connection is saved with your Clipline account, so you only connect once. The YouTube account can be a different Google account from the one you sign in to Clipline with.

**Thumbnails and links on Shorts.** Each Short's description links the full vlog and @mentions the channel (YouTube only lets the @mention be tapped on Shorts). Clipline sets the thumbnail through YouTube for search, the home page and subscriptions (this needs a phone-verified channel, which takes a minute at youtube.com/verify) and puts it in as the first frames of each Short (a fifth of a second). YouTube doesn't let apps set the Shorts-feed picture or the tappable **Related video**, so the Posted page lists two quick Studio steps per Short, with **Download thumbnail** next to **Open in Studio**.

Then tick the Shorts you want and choose when they go out:
- **One a day / two a day**: starting tomorrow, at 12 PM and/or 6 PM your time.
- **Starting on a day and time I choose**: pick the first Short's date and time, and how far apart the rest are.
- **All at once, right away**: posts them now (privacy set by `POST_NOW_PRIVACY` in `.env`).

If posting stops halfway (no internet, YouTube's daily limit), press the button again: Shorts already on YouTube are marked "On YouTube" and are never posted twice.

**Your scheduled Shorts.** **My scheduled Shorts** on the start page (or **On YouTube** in the sidebar) lists every Short Clipline has uploaded, with its live status on YouTube:
- **Change time** moves a scheduled Short to another date and time.
- **Edit Short** opens it on its review screen. Change the title, hook or moment there, then press **Update on YouTube**. A new title is just changed on YouTube. A changed video is uploaded again with the same time and the old upload is deleted, so the link to the Short changes. Clipline won't replace a Short that's already public (it would lose its views and comments).
- A Short Clipline can't find on your channel (deleted in YouTube Studio?) shows **Not found on YouTube**. Click **Unmark it** to upload it again. Shorts on another channel are left alone.

Open Clipline at `http://localhost:8000`, the address it opens by itself. Google only sends you back to the exact address registered in step 4, so `http://127.0.0.1:8000` won't work for Google sign-in. Continue with Google and Connect YouTube both use that one address. When Clipline runs on a server, register that server's address instead (for example `https://clipline.example.com/api/youtube/callback`), set `YOUTUBE_REDIRECT_URI` to the same address, and set `SECRET_KEY`, `DATABASE_PATH` and `SESSION_COOKIE_SECURE=1` in `.env`.

**Things to know about posting**
- **Uploads stay private until your project passes YouTube's API audit.** This is YouTube's rule for new projects. During a trial, open each upload in YouTube Studio and set it to public or scheduled there (Clipline shows an "Open in Studio" link for each one). To lift the limit, apply for the free audit from the YouTube API Services page; you'll need a short privacy policy and a description of the app.
- While the app is in **Testing** mode, a YouTube connection expires after about a week; just connect again when asked. Publishing the app (step 5.5) ends that.
- Each account's YouTube connection is stored in `data/clipline.db` and can post to that channel. Keep the `data` folder private (it's git-ignored). **Disconnect** (under your Shorts) removes it and withdraws the permission at Google; **Switch channel** connects another account.
- Clipline asks to **manage your YouTube videos**, which it needs to show your channel's name, change a scheduled time and replace an edited Short. It only ever touches the Shorts it uploaded. An old `token.json` from earlier versions isn't used any more and can be deleted.
- Custom Shorts thumbnails are rolling out to YouTube Partner Program channels first (since July 2026), and need a phone-verified channel. On other channels YouTube may refuse them. If YouTube refuses, Clipline still uploads the Short and tells you to add the thumbnail in Studio (the file is in the `jobs` folder).

---

## Tips for the best Shorts

- **Use the original export**, not a video downloaded from YouTube. 4K sources give the sharpest vertical crops; a 1080p source works but is softer once cropped.
- Videos where the creator talks to camera give the best results, because both the moment-picking and the face-centred crop rely on speech and a visible face.
- Clipline is made for English vlogs for now. Vlogs in other languages, or mixing Hindi and English, don't come out well yet.
- A 45-minute vlog takes roughly 5–20 minutes on a typical laptop, mostly transcription and editing. On a computer with an NVIDIA graphics card, transcription uses it automatically. The transcript is saved, so it's never transcribed twice for the same job.

## If something goes wrong

| Message | Fix |
|---|---|
| `GEMINI_API_KEY is missing` | Create the `.env` file (step 2) and restart. |
| `Command failed: ffmpeg` | FFmpeg isn't installed or not on PATH (step 1). Reopen the window after installing. |
| Gemini model not found | Google renamed its models. Put a current Flash model name in `GEMINI_MODEL`. |
| Drive link fails | Set sharing to "Anyone with the link", or upload the file instead. |
| Captions use a plain font | Put the font file in `fonts` and make `CAPTION_FONT` match its name. |
| `open() got an unexpected keyword argument 'metadata_errors'` | Fixed: Clipline now reads audio with FFmpeg. Make sure you have the latest code (`git pull`). |
| `module 'cv2' has no attribute 'CascadeClassifier'` | Fixed: Clipline now installs OpenCV 4. Just restart with the start script and it updates itself. |
| Gemini is overloaded / 503 UNAVAILABLE | Google's servers are busy. Clipline retries and tries other models by itself; if it still fails, upload the same video again in a few minutes. The transcript is saved, so it won't be redone. |
| Gemini free usage limit is used up | Wait a while (or until tomorrow) and upload the same video again; the transcript is reused. |
| `No option name near 'captions_1.ass...'` | Your FFmpeg was installed without caption support. Clipline now switches to a complete FFmpeg add-on by itself; restart with the start script so it gets installed. |
| `OPENAI_API_KEY is missing` / OpenAI refused the key | Check `OPENAI_API_KEY` in `.env`, or set `AI_PROVIDER=gemini`. |
| Your OpenAI account has no credit left | Add credit on OpenAI's billing page and try again. |
| Upload says quota exceeded | YouTube's free daily quota is used up. Try again tomorrow. |
| Google says `redirect_uri_mismatch` when signing in | The address isn't registered on your OAuth client. Follow README step 5.4 exactly, and open Clipline at `http://localhost:8000`. |
| Google says "access blocked" | The app is still in Testing. Publish it (step 5.5), or add that Gmail address under **Test users**. |
| "Google hasn't verified this app" when connecting YouTube | Expected until Google verifies Clipline (step 5.5). Click **Advanced → Go to Clipline**. |

## Files

The code is organised by feature, one file each (see `CLAUDE.md` for the full map):

- `app.py`: starts Clipline (loads settings, adds every web feature, runs the server)
- `pipeline/`: making Shorts: transcription, finding moments, editing, captions, hooks, thumbnails
- `youtube/`: Google sign-in, connecting YouTube, uploading, scheduling, reading a vlog's title/description
- `accounts/`: the accounts database (users and their YouTube connections), stored in `data/`
- `web/`: the web routes, one file per feature
- `static/`: the interface: `index.html`, plus `sections/`, `css/` and `js/` (one file per screen or feature)
- `jobs/`: everything Clipline makes, one folder per vlog
- `docs/`: demo video and preview for this README
- `CLAUDE.md`: notes for developers (and Claude): where each feature lives, known gotchas, how to test

## Working on the code

Start with [`CLAUDE.md`](CLAUDE.md). It explains the architecture, the problems already solved (and why),
and how to test without using up Gemini or YouTube quota. Work on a branch and open a pull request:

```bash
git pull --rebase
git checkout -b my-change
# ...edit, then try it with: bash start-mac.command
git add -A && git commit -m "Describe the change"
git push -u origin my-change     # then open the pull request on GitHub
```
