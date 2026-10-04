# CLAUDE.md

Guidance for Claude (and humans) working on this repo. Read this before changing code.

## What Clipline is

A local web app that turns one long vlog into finished vertical YouTube Shorts:
transcribe (faster-whisper) → pick moments (Gemini, or OpenAI with `AI_PROVIDER=openai`) → cut,
reframe to 9:16 around the face, burn in word-by-word captions (FFmpeg + libass) → thumbnail (Pillow)
→ review in the browser → upload and schedule (YouTube Data API v3).

Today it runs on your own computer (the prototype); it is going to the cloud (below). The people using it are
**creators, not developers**:
every error they can see must be plain English and say what to do next.

## Direction: this is going to the cloud

Decided October 2026: Clipline will become a hosted web app. Creators upload from any device and our
servers do the work. The local version is the prototype. **Every change must work the same on a
Linux cloud server as on a laptop:**

- **No code paths for one kind of computer** (no Apple-only, Windows-only or GPU-brand-only engines).
  Use portable libraries that adapt by themselves. For example, faster-whisper uses an NVIDIA GPU
  when present and the processor otherwise.
- **Tune speed with environment settings** (`WHISPER_DEVICE`, `WHISPER_BATCH_SIZE`, `WHISPER_THREADS`,
  `X264_PRESET`, ...), not with `if mac:` branches. A cloud server sets them once.
- **Keep `pipeline/` free of web or UI concerns.** It will become the worker that processes queued
  jobs. Pass everything it needs as arguments or settings.
- **Treat local files as temporary.** The `jobs/` folder will become cloud storage, and in-memory `JOBS`
  will become a database. Don't build features that assume one long-running process on one disk.
- `start-mac.command` / `start-windows.bat` are local-development conveniences only.
- An Apple-GPU (MLX) transcription experiment was set aside for this reason (kept outside git, in
  `_backups/apple-gpu-transcription/`).

## Run it

```bash
cp .env.example .env              # then paste a Gemini key into GEMINI_API_KEY
bash start-mac.command            # Mac (Windows: start-windows.bat)
# → creates .venv, installs requirements.txt, runs app.py, opens http://localhost:8000
```

The start scripts reinstall packages whenever `requirements.txt` differs from
`.venv/installed-requirements.txt`, so **changing requirements.txt is how you ship a dependency fix** to
someone else's machine. Needs Python 3.10+ and FFmpeg/ffprobe on PATH.

Manual run: `.venv/bin/python app.py`. There is no build step and no test suite yet.

## Where things live: one feature per file

The code is split so two people can work on different features without touching the same file.
**A feature usually has up to three files with the same name**: the work in `pipeline/` (or
`youtube/`), the web routes in `web/`, and the page in `static/js/` (+ `static/css/`, `static/sections/`).

| Feature | Work | Web routes | Page |
|---|---|---|---|
| Accounts (email + Google sign-in), `gate()` | `accounts/db.py` | `web/accounts.py` | `js/account.js`, `sections/auth.html`, `css/auth.css` |
| Connect YouTube | `youtube/signin.py`, `youtube/connection.py`, `youtube/config.py` | `web/youtube_connect.py`, `web/google_redirect.py` | `js/youtube-connect.js` |
| Setup form (count, style, must-have moments, file, links) | `youtube/links.py` | `web/make_shorts.py` (`start`), `web/times.py` | `js/setup-form.js`, `js/must-have.js`, `js/video-file.js`, `js/links.js`, `js/start.js`, `sections/setup.html`, `css/setup.css` |
| Vlog title/description from a YouTube link | `youtube/vlog_info.py`, `pipeline/vlog_context.py` | `web/vlog_info.py` | `js/links.js` |
| Making Shorts (the whole run) | all of `pipeline/` | `web/make_shorts.py` | `js/progress.js`, `sections/making.html`, `css/making.css` |
| Transcription (+ saved transcripts) | `pipeline/transcribe.py`, `pipeline/transcript_cache.py` | | |
| Finding moments | `pipeline/moments.py` | | |
| Editing a Short (reframe, captions, render) | `pipeline/reframe.py`, `pipeline/captions.py`, `pipeline/render.py`, `pipeline/fonts.py` | | |
| Thumbnails | `pipeline/thumbnails/` (`make.py` → `design.py`: `frames` → `plan` → `layout` → `looks/<look>.py`; `simple.py`) | | |
| Review cards | | `web/job_status.py`, `web/pages.py` (`/media`) | `js/review.js`, `js/review-cards.js`, `sections/review.html`, `css/review.css` |
| Hooks | `pipeline/hooks.py` | `web/hooks.py` | `js/hooks.js`, `css/hooks.css` |
| Thumbnail look (Frame / Duotone switch) and download | `pipeline/thumbnails/looks/` (one file per look), `make.py` (`relook_thumbnail`) | `web/thumbnail_look.py` | `js/thumbnail-look.js`, `css/thumbnail-look.css` |
| Post page (after review: list, when, where, upload; thumbnail as first frame) | `pipeline/cover.py` | `web/posting.py` | `sections/review.html` (`#postView`), `js/posting.js` (`showPost()`), `css/posting.css` |
| Try again | `pipeline/try_again.py` | `web/try_again.py` | `js/review-cards.js` |
| Add a Short / must-have moments | `pipeline/manual_moment.py` | `web/add_short.py` | `js/review-cards.js` |
| Choose on the video | `pipeline/preview.py` | `web/preview.py` | `js/picker.js`, `sections/picker.html`, `css/picker.css` |
| Upload / schedule | `youtube/upload.py`, `youtube/schedule_times.py` | `web/posting.py` | `js/posting.js`, `css/posting.css` |
| Posted list (step 4) | | | `js/posted.js`, `sections/posted.html`, `css/posted.css` |
| On YouTube page | `youtube/manage.py` | `web/on_youtube.py` | `js/on-youtube.js`, `sections/on-youtube.html`, `css/on-youtube.css` |

**Shared files** (used by many features; change with care and tell the other person):

| File | What it is |
|---|---|
| `app.py` | Starts the server: loads `.env`, imports every `web/` file (that's what registers its routes), runs Flask. |
| `settings.py` | `ROOT` and `JOBS_DIR` (set `JOBS_DIR` in the environment to move the jobs folder, e.g. in tests or the cloud). |
| `web/server.py` | The one Flask `app` every `web/` file adds routes to; cookie/session settings. |
| `web/store.py` | Job state: `JOBS` (in memory) mirrored to `jobs/<id>/job.json`, `LOCK`, `update()`, `update_short()`, `load_job()`, `editable_job()`. |
| `pipeline/ai.py` | `ai_json()`: every AI call (Gemini or OpenAI), with retries and model fallbacks. |
| `pipeline/ffmpeg.py`, `pipeline/text.py`, `pipeline/constants.py` | FFmpeg (`ffmpeg_exe()`, `run()`, `probe()`), small text helpers, shared numbers. |
| `pipeline/__init__.py`, `youtube/__init__.py` | Only re-export what `web/` uses, so web code can write `pipeline.render_short(...)` / `yt.upload_short(...)`. |
| `static/index.html` | The page skeleton: lists the CSS and JS files and includes each `sections/*.html` (the `/` route fills them in). |
| `static/js/core.js` | `$()`, `fmt()`, `esc()`, `show(step)` and the shared page state (`job`, `jobId`, `poll`, `count`). |
| `static/css/tokens.css`, `base.css`, `buttons.css`, `fields.css`, `cards.css`, `shell.css` | The look shared by every screen. |

**Rules for keeping it modular**

- **A new feature gets new files.** Add the work to a new `pipeline/<feature>.py` (or `youtube/`), its routes to a new
  `web/<feature>.py`, its page code to a new `static/js/<feature>.js` (and CSS/section if needed). Then add **one line**
  each to `app.py` (import the web file) and `static/index.html` (the `<script>`/`<link>`/include). Those one-line
  additions are the only shared edits, and git merges them easily.
- Inside `pipeline/` and `youtube/`, import from the feature file directly (`from pipeline.hooks import hook_fields`),
  never from the package `__init__` (that causes circular imports). `web/` uses the facades (`pipeline.x`, `yt.x`).
- `web/` route functions must have unique names: `gate()` in `web/accounts.py` checks `request.endpoint` against
  `PUBLIC`, which lists function names.
- **The page's JS files share one global scope** and load in the order listed in `index.html` (no modules, no build).
  Code that runs while the page loads may only use things defined in the same or an earlier file; anything called
  later (click handlers, polling) can use any file. `account.js` must stay last: it calls `boot()`.
- Where it lives at runtime: `jobs/<id>/` holds each run (`source.*`, `transcript.json`, `captions_N.ass`,
  `short_N.mp4`, `thumb_N.jpg`, `thumbwork_N/`, `preview.mp4`, `job.json`); `jobs/_transcripts/` the transcript
  cache; `data/` the accounts database and cookie secret. All git-ignored.

## Hard-won gotchas (don't undo these)

1. **Audio is decoded with FFmpeg, not faster-whisper's own decoder.** `load_audio()` pipes 16 kHz mono
   float32 from FFmpeg into `model.transcribe(numpy_array)`. faster-whisper's decoder uses PyAV, and
   PyAV ≥ 15 removed the `metadata_errors` argument it passes ("open() got an unexpected keyword
   argument 'metadata_errors'").
2. **OpenCV is pinned below 5** (`opencv-python-headless>=4.8,<5`). OpenCV 5 dropped
   `cv2.CascadeClassifier`, which the face finder uses. `face_center_x()` also catches any failure and
   returns `None`, which means "crop from the centre", so face finding must never fail a job.
3. **Not every FFmpeg can burn captions.** Some builds (recent Homebrew, Anaconda) ship without libass,
   so the `subtitles` filter doesn't exist and FFmpeg says `No option name near 'captions_1.ass...'`.
   `ffmpeg_exe()` uses the first FFmpeg that lists `subtitles` in `-filters`: `$FFMPEG_PATH`, PATH,
   Homebrew paths, then the complete static binary from the `imageio-ffmpeg` package. Always call
   `ffmpeg_exe()` and never hard-code `"ffmpeg"`. (`ffprobe` still comes from PATH.)
4. **Captions need a real font file.** `prepare_job_fonts()` copies `fonts/*.ttf|otf` into the job folder;
   if there are none it copies a system bold font (Arial Bold on Mac). `caption_font_name()` uses
   `CAPTION_FONT` only if that family is actually present, otherwise the family that is. Static FFmpeg
   builds may have no fontconfig, so a missing font can mean invisible captions.
5. **Gemini models are retired often, and they get busy.** `FALLBACK_MODELS` lists current Flash models,
   newest first; `.env` `GEMINI_MODEL` is tried first. `gemini_error_kind()` sorts errors into
   busy / limit / missing / bad_key / other. Busy (5xx) models are retried in rounds (waits in
   `BUSY_WAITS`), while missing and limited models move on to the next one. As of October 2026, the 2.5
   models are restricted to accounts that already used them. Check
   https://ai.google.dev/gemini-api/docs/models before changing names.
6. **ffprobe call is version-agnostic.** `probe()` uses `-show_streams -show_format` and reads rotation
   from `side_data_list` *or* the old `tags.rotate`; `stream_side_data=` in `-show_entries` breaks on
   FFmpeg 4.x.
7. **Sideways phone videos:** `probe()` swaps width/height when rotation is 90/270.
8. The subtitles filter runs with `cwd=job_dir` and relative paths (`subtitles=captions_N.ass:fontsdir=fonts`)
   to avoid Windows drive-letter escaping problems. Keep it that way.

9. **Transcription is batched, and the language is detected across the whole video.** `transcribe()` uses
   faster-whisper's `BatchedInferencePipeline` (about 2× faster; `WHISPER_BATCH_SIZE=0` turns it off and
   falls back to one-at-a-time). Batched mode guesses the language from too little audio: an English
   vlog with car noise came out as **Welsh**. So `detect_language()` votes over 8 clips spread across
   the video and passes the winner in, unless `WHISPER_LANGUAGE` is set (`*.en` models skip this).
   Batched output comes in ~30-second chunks, so `sentence_segments()` rebuilds sentence-sized lines
   from word timings. Gemini needs those to choose good start points. The model is loaded once per
   process (`whisper_model()`), and the GPU is used automatically when present.

10. **Never download videos from YouTube.** YouTube's API policies forbid apps from downloading or storing
    YouTube audiovisual content, even the creator's own, and breaking that risks the API access posting
    depends on. `fetch_video_info()` reads only public text (Data API with `YOUTUBE_API_KEY`, else oEmbed =
    title only). The video always comes from an upload or a Drive link.
11. **AI calls go through `ai_json()`**, which uses Gemini (`gemini_json()`) or OpenAI (`openai_json()`) depending
    on `AI_PROVIDER`. Both share `ask_models()` (retries busy models, skips retired ones) and parse JSON. Use
    it for any new AI feature instead of calling a client directly, and pass images as `image_part(bytes)`.
    OpenAI's JSON mode only returns objects, so a requested list arrives as `{"items": [...]}`; callers must
    accept a dict wrapping the list (as `pick_moments()` does). OpenAI's reasoning models reject
    `temperature`, so `openai_json()` retries without it. `OPENAI_FALLBACK_MODELS` needs the same care as
    `FALLBACK_MODELS` (check https://platform.openai.com/docs/models).
12. **Thumbnails:** one frame of the Short, chosen by the AI, in one of two looks: **Frame** (default,
    colour-graded) or **Duotone** (two-colour poster in the Short's accent). Cut-out collages were dropped in
    October 2026 after a side-by-side test of 8 styles on real Shorts: uneven cut-outs made some thumbnails
    look bad, and they cost a 180 MB model, 2 GB of memory and seconds per thumbnail.
    - **Plan** (`plan.py`): 12 frames (up to 1920 px wide, grabbed 4 at a time) go to the AI, which returns
      `frame`, `focus` (box_2d `[ymin, xmin, ymax, xmax]`, 0-1000, around what must stay in view, usually the
      face), `line1`, `line2` and `accent`. `clean_plan()` validates everything; a missing frame falls back to
      `plan_without_ai()` (biggest sharp face from the face finder, else the sharpest frame).
      **Thumbnails use Gemini whatever `AI_PROVIDER` says** (`THUMB_AI_PROVIDER`): Gemini is trained on box_2d.
      A provider that fails is skipped by every thumbnail for `REST` (180 s) so the others go straight to the
      next one (Gemini was overloaded for minutes in a real run), then no AI.
    - **Text:** `tidy_lines()` drops words from line1 that the headline already has ("Rice Older? / Older
      Than Me" -> "Rice / Older Than Me"), and the prompt asks for that too. `text_spot()` puts the text above
      the face if it fits, else below it (clear of the bottom 230 px where YouTube draws the title), else on
      the roomier side, smaller. Fonts are bundled in `pipeline/thumbnails/fonts/` (OFL): Anton for the
      headline, DM Serif Display for the small line; Latin only, other scripts use the system bold font.
    - **Crop** (`layout.portrait()`): 9:16 around `focus`, a little tighter than the frame height (`ZOOM`) so
      the face can sit at `FACE_AT`; sharpened when blown up a lot (low-resolution vlogs).
    - **Looks:** `compose()` hands the plan to `looks/<look>.py` (`LOOKS`, `THUMB_LOOK`). The look is saved
      in `plan.json`; a creator switches it on the card (`/api/look/...`, redrawn from `thumbwork_N/`, no AI,
      about a second) and can download the thumbnail there. `upgrade_plan()` reads collage-era plans
      (`face_frame`/`face_box`/`items`), which are redrawn as Frame.
    - **Colours:** `fresh_accent()` gives each Short of a vlog a different accent (it reads the other
      `thumbwork_*/plan.json`), chosen under a lock because thumbnails are made side by side.
    - **Speed:** `make_shorts` starts each thumbnail as soon as its Short is edited, `THUMB_WORKERS` (3) at
      once; nearly all of a thumbnail's time is the AI call. Drawing takes ~0.15 s.
    - **Never wait forever on the AI:** every request has a timeout (`ai.TIMEOUT`, 180 s; thumbnails 60 s, no
      busy waits), and thumbnail planning has an overall `AI_DEADLINE` (120 s) after which `plan_without_ai()` is
      used. Without these, one Gemini request that never answered left a job stuck on "Thumbnail 2 of 6".
    Output stays under YouTube's 2 MB thumbnail limit. `THUMB_STYLE=simple` (or a failure) uses `simple.py`.
    - **Shorts feed thumbnail:** the API can't set it (thumbnails.set only covers search, home and
      subscriptions, and needs a phone-verified channel: youtube.com/verify). So `pipeline/cover.py` puts the
      thumbnail in as the first 0.1 s (3 frames) when uploading (`web/posting.upload_file()`) and for the
      Save button (`/media/...?cover=1`); the creator picks that frame in the YouTube app (any channel), or
      uses Download thumbnail + Open in Studio (Partner Program). The cover clip is encoded with the Short's
      own settings and joined without re-encoding (~1 s); if the decode check finds a bad join, it re-encodes.
      Measured: audio and video stay within 0.3 ms. The Short in the job stays clean (Review plays it
      without the flash; upload records keep its name), and `cover_<short>_<thumb>.mp4` is cached.
      `COVER_FRAME=0` turns it off.

13. **Hooks must be true.** Each Short has `hooks` (curiosity / bold / story, plus "custom" if the creator typed
    one), the chosen `hook`, `hook_style` and `hook_mode` ("text" or "none" = no banner, the original audio opens
    it). Every prompt carries `HOOK_RULE` (no invented facts), and `hook_fields()` drops any hook with a number
    that isn't said in the moment ("I lost $2,000" from a clip that never says it). Keep both when changing prompts.
    Applying a hook can also redraw the thumbnail text (`hook_to_lines()` → `retext_thumbnail()`), which reuses
    the thumbnail's saved `thumbwork_N/` frames and `plan.json` (no AI, no new frames).
14. **No emoji in burned-in text.** The caption and thumbnail fonts have no emoji, so they'd show as empty boxes;
    `without_emoji()` strips them in `ass_escape()` and the thumbnail drawers. Titles/descriptions keep them.
15. **YouTube sign-in redirects to `/api/youtube/callback` and must match the OAuth client exactly.** Locally that's
    `http://localhost:8000/...` (not `127.0.0.1`); in the cloud set `YOUTUBE_REDIRECT_URI`. Never go back to
    `InstalledAppFlow.run_local_server()`: it opens a browser on the server and can't work in the cloud. Scopes are
    the single `youtube` scope (upload, channel name, reschedule, title update, delete for Replace); a saved token
    missing it counts as signed out. Replacing an edited Short uploads the new one first, then deletes the old one,
    and is refused once the Short is public (`yt.is_live`). Upload records store `video`, the file that went up, so
    an edit is detected by comparing it with the Short's current `video`.
    The waiting sign-in (state + PKCE verifier + purpose) lives in the user's session cookie, so a callback only
    finishes a sign-in the same browser started. The channel cache `_CHANNEL` is in memory per user.
16. **Accounts and ownership.** Every `/api` and `/media` route needs a signed-in user (`gate()` in `web/accounts.py`;
    only names in `PUBLIC` are open), and any route with a `job_id` checks `job["owner"]` there, so a new job route
    is protected automatically. Background threads have no request, so pass the user id in (as `do_upload` does).
    Google sign-in ("login") asks only `openid email profile` (no cap, no warning); Connect YouTube is separate.
    Users are matched by Google `sub`; an existing account is linked by email only if Google says the email is
    verified, and then any password set earlier is removed and `session_version` bumped (stops pre-account
    hijacking: someone signing up with another person's email first). POSTs from another Origin get 403.
    Tests must set the `DATABASE_PATH` and `JOBS_DIR` environment settings to temporary paths before importing `app`:
    a test once wrote to the real jobs.
    The login throttle keys on `request.remote_addr`; behind a cloud proxy, use the real client IP (ProxyFix).

## Conventions

- Keep it **dependency-light and single-file-per-concern**. No frontend framework. The only database is
  `accounts/db.py` (SQLite from the standard library, accounts and YouTube connections); jobs are still `job.json`
  files. Both are local files for now; in the cloud they need lasting storage (a database server and file storage).
- User-facing errors: raise `RuntimeError("plain sentence about what happened. What to do.")`. They are
  shown in the UI as-is. Log technical detail with `print()` / `traceback.print_exc()` in the terminal.
- Progress: long steps call `progress(pct, "Short message")`; the UI shows the message.
- Settings belong in `.env` (document every new one in `.env.example` and the README), read with
  `os.getenv(NAME, default)`.
- Never commit secrets: `.env`, `client_secret.json`, `token.json` and `data/` are git-ignored. `data/clipline.db`
  holds every user's YouTube connection (can post to real channels) and `data/secret_key` signs sign-in cookies.
- Don't commit media. `jobs/`, `_test/` and font files are ignored (fonts have their own licences).
- After changing Python files, at minimum run: `python -m compileall -q app.py settings.py pipeline youtube accounts web`
  and start the app once (an import error in any `web/` file stops it from starting).

## Testing without burning API quota

There are no automated tests yet. These manual checks work well:

- **Short clip:** `ffmpeg -ss 300 -i long.mp4 -t 90 -c copy test90.mp4` and upload that in the UI.
- **Skip Gemini:** monkeypatch `google.genai.Client` with a fake whose `models.generate_content()`
  returns `types.SimpleNamespace(text='[{"start": 17.5, "end": 45.8, "hook": "...", "title": "...",
  "thumb_line1": "...", "thumb_line2": "...", "why": "...", "hashtags": ["a","b","c"]}]')`, then call
  `pipeline.pick_moments(transcript, n)` or drive the whole app with `app.app.test_client()`.
- **Encoder speed:** `X264_PRESET` defaults to `veryfast` (CRF 18): measured 2.5x faster than `medium` with a
  slightly smaller file and SSIM 0.994 against it (no visible difference). `ultrafast` and `WHISPER_MODEL=base`
  speed up testing further.
- **Look at the output:** grab frames with `ffmpeg -ss 1.2 -i jobs/<id>/short_1.mp4 -frames:v 1 f.jpg`
  and check that the captions, yellow word highlight, hook banner and face crop are all present.

Good first automated tests to add: `clean_moments()` (overlaps, length limits, word snapping),
`build_ass()` (timing never goes backwards), `gemini_error_kind()`, `crop_filter()`, `plan_times()`.

## Working together (two people)

- `main` should always run. Work on a branch (`git checkout -b fix-captions`), push it, open a pull
  request, and let the other person look before merging. Never merge into `main` locally or push to it
  directly: changes reach `main` only through a pull request that Saumya or Nesh merges on GitHub.
- **No AI attribution in git.** Commits and pull requests are authored by Saumya or Nesh only: never add
  `Co-Authored-By: Claude ...`, `Claude-Session: ...`, "Generated with Claude Code" or similar lines to
  commit messages or PR descriptions. (This repo's history was cleaned of them in October 2026.)
- Pull before you start: `git pull --rebase`.
- If you change `requirements.txt`, say so in the PR. The other person's start script will reinstall
  automatically on the next launch.
- Each person keeps their own `.env` (Gemini/OpenAI keys), `client_secret.json` and `data/` (accounts and YouTube
  connections). Never share these through git.
- Work on different features = different files (see "Where things live"). If you both need a shared file, keep the
  change small and say so in the PR.

## Ideas / known limits

- Transcription speed: before batching, `WHISPER_MODEL=small` on CPU took about 9 min for a 40-min vlog on an
  M-series Mac; batching roughly halves that. A GPU cloud server is much faster still.
- Low-resolution sources (e.g. 640×360 YouTube downloads) give soft Shorts; use original exports.
- New YouTube API projects can only upload as **private** until Google's audit is passed (see README).
- Custom thumbnails for Shorts only work on channels YouTube has enabled them for.
