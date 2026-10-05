# Pit Crew

*Formerly Clipline. The code folder and the GitHub repository are still called `clipline`.*

Turn one long vlog into finished YouTube Shorts: it finds the best moments, cuts them vertical around the creator's face, burns in word-by-word captions with an on-screen hook, makes a thumbnail for each, lets you play and approve them, then uploads and schedules them on the channel.

Everything runs on your own computer with free tools. The only accounts you need are a free Gemini API key (or an OpenAI key) and (for auto-posting) a free Google Cloud project.

<p align="center">
  <a href="docs/demo.mp4"><img src="docs/demo.gif" width="240" alt="Pit Crew demo: a creator's long edit turns into a stack of ready-to-post Shorts"></a>
  <br><sub>▶ <a href="docs/demo.mp4">Watch the demo video</a> (10 s)</sub>
</p>

## What happens when you click "Make my Shorts"

1. **Transcribe.** faster-whisper (open-source Whisper) writes down every word with exact timings. Runs on your computer.
2. **Find moments.** Gemini reads the full transcript (plus the vlog's title and description, if you give them) and picks the strongest stand-alone moments, with a hook, title, thumbnail text and hashtags for each, written in the creator's tone.
3. **Edit.** FFmpeg cuts each moment, crops to 9:16 centred on the face, and burns in captions in the style you chose. Output is 1080×1920, high quality (CRF 18).
4. **Thumbnails.** Gemini (always Gemini, even when OpenAI picks the moments) looks at frames from each Short, picks the best moment (sharp, a strong reaction, or the thing the Short is about) and writes a short two-line text. Pit Crew crops it to the Shorts shape around the face and adds the text in the style creators use. Each Short has two looks you can switch between on its card in Review: **Frame** (the moment itself, colour-graded, the default) and **Duotone** (a two-colour poster in that Short's own colour). The download button next to them saves the thumbnail.
5. **Review.** You play every Short in the browser, edit titles, untick any you don't want. Not happy with one? **Try again** picks a different moment (optionally from your description or exact times). **Add a Short** makes one from a moment the AI missed. Under **Hook**, choose between three opening texts (Curiosity, Bold, Story), type your own, ask for new ones, or turn the text off so your own words open the Short. In both, **Choose on the video** lets you play through the vlog and mark the start and end yourself, which is the way to get scenes without talking (the AI only knows what's said).

Before you start, you can also tell Pit Crew what you want ("include the summit, skip the drive") and add **must-have moments** by their times; those always become Shorts and the AI picks the rest.
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

At this point you can already make, play, and download Shorts. Step 5 only adds automatic posting.

**Accounts.** The first screen asks you to sign in. Create an account with your email and a password (at least
8 characters), or use **Continue with Google** once step 5 is done. Each account sees only its own vlogs, Shorts
and YouTube channel. Vlogs made before Pit Crew had accounts belong to the first account created. **Forgot
password?** emails a reset link (step 7; until then the link is printed in the Terminal window).

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

**Your scheduled Shorts.** **My scheduled posts** on the start page (or **Scheduled** in the sidebar, which also lists Reels planned for Instagram) lists every Short Pit Crew has uploaded, with its live status on YouTube:
- **Change time** moves a scheduled Short to another date and time.
- **Edit Short** opens it on its review screen. Change the title, hook or moment there, then press **Update on YouTube**. A new title is just changed on YouTube. A changed video is uploaded again with the same time and the old upload is deleted, so the link to the Short changes. Pit Crew won't replace a Short that's already public (it would lose its views and comments).
- A Short Pit Crew can't find on your channel (deleted in YouTube Studio?) shows **Not found on YouTube**. Click **Unmark it** to upload it again. Shorts on another channel are left alone.

Open Pit Crew at `http://localhost:8000`, the address it opens by itself. Google only sends you back to the exact address registered in step 4, so `http://127.0.0.1:8000` won't work for Google sign-in. Continue with Google and Connect YouTube both use that one address. When Pit Crew runs on a server, register that server's address instead (for example `https://pitcrew.example.com/api/youtube/callback`), set `YOUTUBE_REDIRECT_URI` to the same address, and set `SECRET_KEY`, `DATABASE_PATH` and `SESSION_COOKIE_SECURE=1` in `.env`.

**Analytics.** **Analytics** in the sidebar shows how every Short on your channel is doing: views, watch time, likes, comments, shares, subscribers, a views-per-day chart, top Shorts (click one for its retention curve), how viewers find you, countries, age and gender, plus Instagram Reels once Instagram is connected. If you connected YouTube before Analytics existed, click **Connect again** there once so Pit Crew can read YouTube Analytics.

**Things to know about posting**
- **Uploads stay private until your project passes YouTube's API audit.** This is YouTube's rule for new projects. During a trial, open each upload in YouTube Studio and set it to public or scheduled there (Pit Crew shows an "Open in Studio" link for each one). To lift the limit, apply for the free audit from the YouTube API Services page; you'll need a short privacy policy and a description of the app.
- While the app is in **Testing** mode, a YouTube connection expires after about a week; just connect again when asked. Publishing the app (step 5.5) ends that.
- Each account's YouTube connections are stored in `data/clipline.db` and can post to those channels. Keep the `data` folder private (it's git-ignored). **Disconnect** removes one channel and withdraws the permission at Google.
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

**Posting Reels.** Each Short gets its own Instagram schedule: **Same times as YouTube**, the same presets, a custom start and spacing, or right away. Instagram doesn't let apps schedule posts, so Pit Crew posts each Reel itself at its time: keep Pit Crew running (Reels that came due while it was closed go out when it starts again). The caption has the title, the hook, the full video's name on YouTube and the hashtags; the Short's thumbnail frame becomes the Reel cover. Instagram allows 100 posts by app per account per day. If posting stops, the Reel shows **Try again**; if Pit Crew was closed in the middle of posting, check Instagram first so nothing is posted twice.

### 7. Send password reset emails (optional)

When someone clicks **Forgot password?** on the sign-in screen, Pit Crew emails them a link to choose a new password (it works once, for 1 hour). Until email is set up, no email goes out and the link is printed in the Terminal window instead, which is fine on your own computer.

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

Any other email service with SMTP works the same way (put its host, port, user and password instead). On a server, also set `APP_URL` to Pit Crew's public address so the link points to the right place.

**Signing in with Google when you made your account with a password:** Pit Crew shows "Email already exists" in red and doesn't join the two. Sign in with your email and password (or use Forgot password).

---

## Tips for the best Shorts

- **Use the original export**, not a video downloaded from YouTube. 4K sources give the sharpest vertical crops; a 1080p source works but is softer once cropped.
- Videos where the creator talks to camera give the best results, because both the moment-picking and the face-centred crop rely on speech and a visible face.
- Pit Crew is made for English vlogs for now. Vlogs in other languages, or mixing Hindi and English, don't come out well yet.
- A 45-minute vlog takes roughly 5–20 minutes on a typical laptop, mostly transcription and editing. On a computer with an NVIDIA graphics card, transcription uses it automatically. The transcript is saved, so it's never transcribed twice for the same job.

## If something goes wrong

| Message | Fix |
|---|---|
| `GEMINI_API_KEY is missing` | Create the `.env` file (step 2) and restart. |
| `Command failed: ffmpeg` | FFmpeg isn't installed or not on PATH (step 1). Reopen the window after installing. |
| Gemini model not found | Google renamed its models. Put a current Flash model name in `GEMINI_MODEL`. |
| Drive link fails | Set sharing to "Anyone with the link", or upload the file instead. |
| Captions use a plain font | Put the font file in `fonts` and make `CAPTION_FONT` match its name. |
| `open() got an unexpected keyword argument 'metadata_errors'` | Fixed: Pit Crew now reads audio with FFmpeg. Make sure you have the latest code (`git pull`). |
| `module 'cv2' has no attribute 'CascadeClassifier'` | Fixed: Pit Crew now installs OpenCV 4. Just restart with the start script and it updates itself. |
| Gemini is overloaded / 503 UNAVAILABLE | Google's servers are busy. Pit Crew retries and tries other models by itself; if it still fails, upload the same video again in a few minutes. The transcript is saved, so it won't be redone. |
| Gemini free usage limit is used up | Wait a while (or until tomorrow) and upload the same video again; the transcript is reused. |
| `No option name near 'captions_1.ass...'` | Your FFmpeg was installed without caption support. Pit Crew now switches to a complete FFmpeg add-on by itself; restart with the start script so it gets installed. |
| `OPENAI_API_KEY is missing` / OpenAI refused the key | Check `OPENAI_API_KEY` in `.env`, or set `AI_PROVIDER=gemini`. |
| Your OpenAI account has no credit left | Add credit on OpenAI's billing page and try again. |
| Upload says quota exceeded | YouTube's free daily quota is used up. Try again tomorrow. |
| Google says `redirect_uri_mismatch` when signing in | The address isn't registered on your OAuth client. Follow README step 5.4 exactly, and open Pit Crew at `http://localhost:8000`. |
| Google says "access blocked" | The app is still in Testing. Publish it (step 5.5), or add that Gmail address under **Test users**. |
| "Google hasn't verified this app" when connecting YouTube | Expected until Google verifies Pit Crew (step 5.5). Click **Advanced → Go to Pit Crew**. |

## Files

The code is organised by feature, one file each (see `CLAUDE.md` for the full map):

- `app.py`: starts Pit Crew (loads settings, adds every web feature, runs the server)
- `pipeline/`: making Shorts: transcription, finding moments, editing, captions, hooks, thumbnails
- `youtube/`: Google sign-in, connecting YouTube, uploading, scheduling, reading a vlog's title/description, analytics
- `instagram/`: connecting Instagram, posting Reels, Reel insights
- `accounts/`: the accounts database (users and their YouTube and Instagram connections), stored in `data/`
- `web/`: the web routes, one file per feature
- `static/`: the interface: `index.html`, plus `sections/`, `css/` and `js/` (one file per screen or feature)
- `jobs/`: everything Pit Crew makes, one folder per vlog
- `docs/`: demo video and preview for this README
- `CLAUDE.md`: notes for developers (and Claude): where each feature lives, known gotchas, how to test

## Working on the code

Start with [`CLAUDE.md`](CLAUDE.md). It explains the architecture, the problems already solved (and why),
and how to test without using up Gemini or YouTube quota. Each person has one branch (Saumya `saumya`,
Nesh `nesh`; no other branches) and changes reach `main` only through a pull request:

```bash
git checkout saumya                # or nesh
git fetch origin && git merge origin/main   # level with main first
# ...edit, then try it with: bash start-mac.command
git add -A && git commit -m "Describe the change"
git push                           # then open the pull request (saumya -> main) on GitHub
```
