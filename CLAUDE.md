# CLAUDE.md

Guidance for Claude (and humans) working on this repo. Read this before changing code.

## What Clipline is

A local web app that turns one long vlog into finished vertical YouTube Shorts:
transcribe (faster-whisper) → pick moments (Gemini, or OpenAI with `AI_PROVIDER=openai`) → cut,
reframe to 9:16 around the face, burn in word-by-word captions (FFmpeg + libass) → thumbnail (Pillow)
→ review in the browser → upload and schedule (YouTube Data API v3).

Everything runs on the user's own computer. The people using it are **creators, not developers**:
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
- **Keep `pipeline.py` free of web or UI concerns.** It will become the worker that processes queued
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

## Files

| File | What it does |
|---|---|
| `app.py` | Flask server (127.0.0.1:8000). `/api/start` saves the upload and runs `make_shorts()` in a background thread; `/api/status/<id>` is polled every second by the page; `/api/retry/<id>/<idx>` remakes one Short and `/api/add/<id>` adds one (both run `remake_short()` in a thread, one at a time per job); `/api/hooks/<id>/<idx>` writes 3 new hook options and `/api/hook/<id>/<idx>` re-renders one Short with a chosen hook (or none), reusing its saved face position `cx`; `/api/preview/<id>` makes `preview.mp4` for choosing a scene on the video (also started when a job finishes); accounts: `/api/me`, `/api/auth/signup|login|logout`, `/api/auth/google` (Continue with Google, full-page redirect); `/api/youtube/signin` → Google → `/api/youtube/callback` connects the user's YouTube (in a popup; the callback also finishes Google sign-in), `/api/youtube/me` / `/api/youtube/signout`; `/api/schedule/<id>` uploads (refused until signed in; skips Shorts already in `uploads`, so a retry never posts twice; plans times in the browser's time zone `tz`); `/api/posted` lists every upload across jobs with live YouTube state (the "On YouTube" page), `/api/reschedule/<id>/<idx>` changes a scheduled time and `/api/repost/<id>/<idx>` updates a posted Short after an edit. Job state lives in memory (`JOBS`) and is mirrored to `jobs/<id>/job.json`. |
| `pipeline.py` | All media work: `probe`, `load_audio`, `transcribe`, `pick_moments` / `clean_moments`, `repick_moment` (Try again), `manual_moment` (creator's own times; the AI only writes the text), `make_preview` (small H.264 copy every browser can play; `-hwaccel auto` uses video hardware when present), `face_center_x`, `build_ass`, `render_short`, `make_thumbnail`, plus `ffmpeg_exe()` (chooses which FFmpeg to use). |
| `thumbnails.py` | Collage thumbnails: `sample_frames()` → `plan()` (Gemini sees ~10 frames, returns the face frame, up to 3 items with `box_2d`, text, accent) or `plan_without_ai()` → `cut_out()` (rembg) → `compose()`. Called from `pipeline.make_thumbnail()`, which falls back to `make_simple_thumbnail()`. |
| `db.py` | SQLite accounts database (`data/clipline.db`, `DATABASE_PATH`): `users` (email, password hash, Google `sub`, `session_version`) and `youtube_tokens` (one YouTube connection per user); `secret_key()` for the session cookie. |
| `youtube_upload.py` | Google OAuth in the app for two purposes sharing one callback: `start_google("login"|"youtube")`, `finish_login()` (verifies the ID token) and `finish_youtube()` (checks the granted scope, saves the user's connection via `_read_token`/`_save_token`/`_drop_token(user_id)`), `account()` (signed in + channel name), `sign_out()`, `plan_times()` for the schedule (presets or a custom start + spacing, in the creator's time zone), `upload_short()`, `upload_error_message()`, and `fetch_video_info()` (title/description/tags of a vlog from its link). |
| `static/index.html` | The whole UI: one file, vanilla JS, no build. |
| `start-mac.command`, `start-windows.bat` | One-click launchers (venv + install + run). |
| `jobs/<id>/` | Per-run output: `source.*`, `transcript.json`, `captions_N.ass`, `short_N.mp4`, `thumb_N.jpg`, `preview.mp4`, `job.json`. Git-ignored. |
| `jobs/_transcripts/<fingerprint>.json` | Transcript cache keyed by a hash of the video (size + first/last 4 MB), so re-uploading the same vlog skips transcription. |

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
12. **Thumbnails:** Gemini's `box_2d` is `[ymin, xmin, ymax, xmax]` on a 0-1000 scale. `clean_plan()` validates
    everything Gemini returns. The face cut-out crops ~1.2 face-widths either side first and splits thin
    bridges (erode → pick the blob under the face → dilate), so people next to the creator aren't included;
    overlapping people can still leak in, which is why the prompt asks for frames with the creator alone.
    "scene" items become photo cards and "object" items become stickers; a cut-out covering <4% or >92% of
    the crop counts as failed and becomes a card. Output stays under YouTube's 2 MB thumbnail limit.
    Gemini is trained on `box_2d`; OpenAI models are asked for the same format but place boxes less
    precisely, so expect looser item cut-outs with `AI_PROVIDER=openai`.
    rembg downloads its model (~180 MB) on first use into `U2NET_HOME` (default `~/.u2net`); bake it into the
    server image in the cloud.

13. **Hooks must be true.** Each Short has `hooks` (curiosity / bold / story, plus "custom" if the creator typed
    one), the chosen `hook`, `hook_style` and `hook_mode` ("text" or "none" = no banner, the original audio opens
    it). Every prompt carries `HOOK_RULE` (no invented facts), and `hook_fields()` drops any hook with a number
    that isn't said in the moment ("I lost $2,000" from a clip that never says it). Keep both when changing prompts.
    Applying a hook can also redraw the thumbnail text (`hook_to_lines()` → `retext_thumbnail()`), which reuses
    the collage's saved `thumbwork_N/` frames and `plan.json` (no AI, no new frames).
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
16. **Accounts and ownership.** Every `/api` and `/media` route needs a signed-in user (`gate()` in `app.py`;
    only names in `PUBLIC` are open), and any route with a `job_id` checks `job["owner"]` there, so a new job route
    is protected automatically. Background threads have no request, so pass the user id in (as `do_upload` does).
    Google sign-in ("login") asks only `openid email profile` (no cap, no warning); Connect YouTube is separate.
    Users are matched by Google `sub`; an existing account is linked by email only if Google says the email is
    verified, and then any password set earlier is removed and `session_version` bumped (stops pre-account
    hijacking: someone signing up with another person's email first). POSTs from another Origin get 403.
    Tests must set `DATABASE_PATH` and `app.JOBS_DIR` to temporary paths: a test once wrote to the real jobs.
    The login throttle keys on `request.remote_addr`; behind a cloud proxy, use the real client IP (ProxyFix).

## Conventions

- Keep it **dependency-light and single-file-per-concern**. No frontend framework. The only database is
  `db.py` (SQLite from the standard library, accounts and YouTube connections); jobs are still `job.json` files.
- User-facing errors: raise `RuntimeError("plain sentence about what happened. What to do.")`. They are
  shown in the UI as-is. Log technical detail with `print()` / `traceback.print_exc()` in the terminal.
- Progress: long steps call `progress(pct, "Short message")`; the UI shows the message.
- Settings belong in `.env` (document every new one in `.env.example` and the README), read with
  `os.getenv(NAME, default)`.
- Never commit secrets: `.env`, `client_secret.json`, `token.json` and `data/` are git-ignored. `data/clipline.db`
  holds every user's YouTube connection (can post to real channels) and `data/secret_key` signs sign-in cookies.
- Don't commit media. `jobs/`, `_test/` and font files are ignored (fonts have their own licences).
- After changing Python files, at minimum run: `python -m py_compile app.py pipeline.py youtube_upload.py`.

## Testing without burning API quota

There are no automated tests yet. These manual checks work well:

- **Short clip:** `ffmpeg -ss 300 -i long.mp4 -t 90 -c copy test90.mp4` and upload that in the UI.
- **Skip Gemini:** monkeypatch `google.genai.Client` with a fake whose `models.generate_content()`
  returns `types.SimpleNamespace(text='[{"start": 17.5, "end": 45.8, "hook": "...", "title": "...",
  "thumb_line1": "...", "thumb_line2": "...", "why": "...", "hashtags": ["a","b","c"]}]')`, then call
  `pipeline.pick_moments(transcript, n)` or drive the whole app with `app.app.test_client()`.
- **Faster renders while testing:** `X264_PRESET=veryfast` (or `ultrafast`) and `WHISPER_MODEL=base`.
- **Look at the output:** grab frames with `ffmpeg -ss 1.2 -i jobs/<id>/short_1.mp4 -frames:v 1 f.jpg`
  and check that the captions, yellow word highlight, hook banner and face crop are all present.

Good first automated tests to add: `clean_moments()` (overlaps, length limits, word snapping),
`build_ass()` (timing never goes backwards), `gemini_error_kind()`, `crop_filter()`, `plan_times()`.

## Working together (two people)

- `main` should always run. Work on a branch (`git checkout -b fix-captions`), push it, open a pull
  request, and let the other person look before merging.
- Pull before you start: `git pull --rebase`.
- If you change `requirements.txt`, say so in the PR. The other person's start script will reinstall
  automatically on the next launch.
- Each person keeps their own `.env`, Gemini key, `client_secret.json` and `token.json`. Never share
  these through git.

## Ideas / known limits

- Transcription speed: before batching, `WHISPER_MODEL=small` on CPU took about 9 min for a 40-min vlog on an
  M-series Mac; batching roughly halves that. A GPU cloud server is much faster still.
- Low-resolution sources (e.g. 640×360 YouTube downloads) give soft Shorts; use original exports.
- New YouTube API projects can only upload as **private** until Google's audit is passed (see README).
- Custom thumbnails for Shorts only work on channels YouTube has enabled them for.
