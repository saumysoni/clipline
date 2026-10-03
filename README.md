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
4. **Thumbnails.** Gemini looks at frames from each Short and picks the best reaction shot plus the things worth showing (food, places, vehicles...). Clipline cuts the creator out with a bright glowing outline, adds the other things as cut-out stickers or tilted photo cards (a collage), and puts bold text on top.
5. **Review.** You play every Short in the browser, edit titles, untick any you don't want.
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

The first run installs everything and downloads the speech model (around 500 MB) and, at the first thumbnail, the cut-out model (around 180 MB), so give it a few minutes. Your browser then opens **http://localhost:8000**. Keep the black window open while you use it.

At this point you can already make, play, and download Shorts. Step 5 only adds automatic posting.

### 5. Turn on automatic YouTube posting

1. Go to https://console.cloud.google.com and create a project (free, no card needed).
2. **APIs & Services → Library**: search **YouTube Data API v3** and click **Enable**.
3. **OAuth consent screen**: choose **External**, fill in the app name and your email. Under **Test users**, add the Gmail address of the creator's YouTube channel.
4. **Credentials → Create credentials → OAuth client ID → Desktop app**. Download the JSON file, rename it to `client_secret.json`, and put it in the Clipline folder.
5. Restart Clipline. The top-right badge should say "YouTube posting is set up".

The first time you click **Schedule**, a Google sign-in page opens. The creator signs in with her channel account and clicks Allow. Clipline saves that permission in `token.json`.

**Things to know about posting**
- **Uploads stay private until your project passes YouTube's API audit.** This is YouTube's rule for new projects. During a trial, open each upload in YouTube Studio and set it to public or scheduled there (Clipline shows an "Open in Studio" link for each one). To lift the limit, apply for the free audit from the YouTube API Services page; you'll need a short privacy policy and a description of the app.
- While the consent screen is in **Testing** mode, the sign-in expires after about a week; just sign in again when asked.
- `token.json` gives this computer permission to post on that channel. Only keep it on a computer you trust, and delete it to disconnect. To switch to another creator's channel, delete `token.json` and sign in with their account.
- Custom Shorts thumbnails are rolling out to YouTube Partner Program channels first (since July 2026), and need a phone-verified channel. On other channels YouTube may refuse them. If YouTube refuses, Clipline still uploads the Short and tells you to add the thumbnail in Studio (the file is in the `jobs` folder).

---

## Tips for the best Shorts

- **Use the original export**, not a video downloaded from YouTube. 4K sources give the sharpest vertical crops; a 1080p source works but is softer once cropped.
- Videos where the creator talks to camera give the best results, because both the moment-picking and the face-centred crop rely on speech and a visible face.
- For non-English or mixed-language vlogs, set `WHISPER_LANGUAGE` in `.env`, or use `WHISPER_MODEL=medium` for better accuracy.
- A 45-minute vlog takes roughly 5–20 minutes on a typical laptop, mostly transcription and editing. On a computer with an NVIDIA graphics card, transcription uses it automatically. The transcript is saved, so it's never transcribed twice for the same job.

## If something goes wrong

| Message | Fix |
|---|---|
| `GEMINI_API_KEY is missing` | Create the `.env` file (step 2) and restart. |
| `Command failed: ffmpeg` | FFmpeg isn't installed or not on PATH (step 1). Reopen the window after installing. |
| Gemini model not found | Google renamed its models. Put a current Flash model name in `GEMINI_MODEL`. |
| Drive link fails | Set sharing to "Anyone with the link", or upload the file instead. |
| Captions use a plain font | Put the font file in `fonts` and make `CAPTION_FONT` match its name. |
| `open() got an unexpected keyword argument 'metadata_errors'` | Fixed: Clipline now reads audio with FFmpeg. Make sure you have the latest `pipeline.py`. |
| `module 'cv2' has no attribute 'CascadeClassifier'` | Fixed: Clipline now installs OpenCV 4. Just restart with the start script and it updates itself. |
| Gemini is overloaded / 503 UNAVAILABLE | Google's servers are busy. Clipline retries and tries other models by itself; if it still fails, upload the same video again in a few minutes. The transcript is saved, so it won't be redone. |
| Gemini free usage limit is used up | Wait a while (or until tomorrow) and upload the same video again; the transcript is reused. |
| `No option name near 'captions_1.ass...'` | Your FFmpeg was installed without caption support. Clipline now switches to a complete FFmpeg add-on by itself; restart with the start script so it gets installed. |
| `OPENAI_API_KEY is missing` / OpenAI refused the key | Check `OPENAI_API_KEY` in `.env`, or set `AI_PROVIDER=gemini`. |
| Your OpenAI account has no credit left | Add credit on OpenAI's billing page and try again. |
| Upload says quota exceeded | YouTube's free daily quota is used up. Try again tomorrow. |

## Files

- `app.py`: the local web app (starts the server, runs jobs, handles posting)
- `pipeline.py`: transcription, moment picking, editing
- `thumbnails.py`: collage thumbnails (frame picking with Gemini, cut-outs, layout)
- `youtube_upload.py`: YouTube sign-in, upload, scheduling, and reading a vlog's title/description from its link
- `static/index.html`: the interface
- `jobs/`: everything Clipline makes, one folder per vlog
- `docs/`: demo video and preview for this README
- `CLAUDE.md`: notes for developers (and Claude): how the code fits together, known gotchas, how to test

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
