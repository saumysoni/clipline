# Reviews: what to paste into Google's and Meta's forms

Pit Crew needs three approvals before anyone outside the beta can use it (LAUNCH.md section 10). This file has the text
for each form and a shot list for each demo video, written from what the code actually does. Replace `<domain>` with
the site's domain (e.g. `pitcrewapp.me`) and `<support email>` with `SUPPORT_EMAIL`.

**Before submitting anything:**

- [ ] The site is live at `https://<domain>`, and `/welcome`, `/privacy`, `/terms` and `/data-deletion` open.
- [ ] **Gemini is on a paid plan and `GEMINI_PAID=1` is set.** Pit Crew sends a vlog's YouTube title and description
      (moment picking) and the creator's YouTube numbers (Pit Crew's daily read on Analytics) to the AI. Google's Limited
      Use rules forbid Google user data being used to train AI models, and Gemini's free plan allows Google to use what it
      receives to improve its products. With `OPENAI_API_KEY` as well, OpenAI's API terms already exclude training.
- [ ] The privacy policy mentions every scope below (it does, `static/legal/privacy.html`), and its date is current.
- [ ] A reviewer can get in: add the reviewers' sign-in to the invite list, or give them a test account (below). Never
      put a real creator's password in a form.

---

## 1. Google: OAuth app verification (sensitive scopes)

Google Cloud console → Google Auth Platform. Google says it typically takes 3–5 business days.

**Branding**

| Field | Value |
|---|---|
| App name | Pit Crew |
| User support email | `<support email>` |
| App logo | `docs/logo.svg` exported as a 120×120 PNG |
| Application home page | `https://<domain>/welcome` |
| Privacy policy | `https://<domain>/privacy` |
| Terms of service | `https://<domain>/terms` |
| Authorized domains | `<domain>` (verify it first in Google Search Console with a DNS TXT record) |
| Developer contact | your own email |

**Clients → the Web client:** authorized redirect URI `https://<domain>/api/youtube/callback` (sign-in and YouTube use the
same one); JavaScript origin `https://<domain>`.

**Data access (scopes)** and the justification Google asks for, one per scope:

`openid`, `.../auth/userinfo.email`, `.../auth/userinfo.profile` (non-sensitive):
> Used only for "Continue with Google" on Pit Crew's sign-in screen: we read the Google account's ID, email address and
> name to create and sign in to the user's Pit Crew account.

`https://www.googleapis.com/auth/youtube` (sensitive):
> Pit Crew is a tool for YouTube creators: it turns a long vlog the creator uploads into short vertical clips and posts
> them to the creator's own channel. With this scope Pit Crew, only when the creator presses a button: uploads the clips
> and vlogs they chose (videos.insert) and sets the custom thumbnail of a vlog (thumbnails.set); schedules them as
> private videos that go public at the time they picked (status.publishAt); lets them change a scheduled time or a title
> later from Pit Crew's Scheduled page (videos.update); replaces a clip they re-edited after uploading by uploading the
> new version and deleting the old one, only while it isn't public yet, and deletes a clip Pit Crew posted when the
> creator chooses Delete on it in Pit Crew and confirms (videos.delete); checks whether a video Pit Crew
> posted still exists, so one deleted in YouTube Studio isn't shown as posted (videos.list); and shows the connected
> channel's name and picture (channels.list). A narrower scope isn't enough: youtube.upload can't change a scheduled
> time, edit a title or delete a clip, and youtube.readonly can't upload.

`https://www.googleapis.com/auth/yt-analytics.readonly` (sensitive):
> Pit Crew's Analytics page shows the creator how the clips it posted are doing: views, watch time, likes, comments,
> shares, subscribers gained, traffic sources and audience (age, gender, country) for their own channel, compared with
> the same clips on Instagram, and each clip's first-week views. The data is read when the page opens, shown only to that
> creator, kept only in memory (minutes to at most 30 days) and never sold, shared or used for advertising. This scope is
> optional: a creator who doesn't grant it can still post.

**How the data is protected** (Google sometimes asks):
> Tokens are encrypted at rest (Fernet, key outside the database and outside backups). The site is https only, with
> HSTS. Each creator only ever sees their own data. Stored YouTube data (video IDs of posted clips, channel name and
> picture) is checked against YouTube at least weekly, and deleted within 7 days of the creator disconnecting the channel
> in Pit Crew and within 14 days of a removal in Google's security settings. Deleting the Pit Crew account deletes
> everything at once and revokes the token at Google.

### Demo video (unlisted on YouTube, about 3–5 minutes, English, no music needed)

Record the browser with the address bar visible the whole time. Use a test channel, not a creator's.

1. Open `https://<domain>/welcome`, then the privacy policy link (show it briefly).
2. Click **Continue with Google**. On Google's consent screen, show the address bar: **zoom in on `client_id=`** so it
   can be read, and show the app name "Pit Crew". Finish signing in.
3. In the sidebar, **Connect YouTube**. Show the consent screen again with both YouTube permissions listed and the
   `client_id` in the address bar. Grant both.
4. **youtube scope, uploading:** make Shorts from a short test vlog (prepare one beforehand so it's ready), open Review,
   then Post: schedule two clips. Then open **YouTube Studio** in another tab and show them there, scheduled.
5. **youtube scope, editing:** on Pit Crew's **Scheduled** page, change one clip's time and its title; refresh Studio to
   show the change. Then edit a clip's caption in Pit Crew and use **Replace** to show the old version is deleted.
   Then on **Shorts & Reels**, open a posted test clip's ⋮ › **Delete**, tick YouTube, confirm, and refresh Studio to
   show it's gone.
6. **youtube scope, vlog upload:** + Create → Upload a vlog → upload with a thumbnail; show it in Studio.
7. **yt-analytics.readonly:** open **Analytics**: the Overview tiles and chart, the Videos tab, the Audience tab.
8. **Your choices:** Settings → **Disconnect** the channel; then show Google's security settings page listing Pit Crew
   (and that it can be removed there).

Put the video's link in the verification form, together with the scope justifications above.

---

## 2. YouTube API Services: audit and quota extension

Form: "YouTube API Services - Audit and Quota Extension Form" (linked from the YouTube Data API quota page). Until it's
passed, uploads from Pit Crew stay **private** and the whole app has the default quota. It's free. Have ready:

- **What the app does:** the same description as the `youtube` scope above, plus the homepage, privacy and terms links.
- **Who uses it:** YouTube creators posting to channels they own or manage. No public data from other channels is
  shown, collected or stored. Pit Crew never downloads videos from YouTube: vlogs are uploaded by the creator.
- **API calls:** videos.insert, videos.update, videos.delete, videos.list, thumbnails.set, channels.list (Data API v3);
  reports.query (Analytics API v2). Optional: videos.list with an API key to read the title and description of a vlog
  link the creator pastes.
- **Expected volume (for the quota request):** each creator posts about 5–10 clips per vlog, a few vlogs a week. Ask for
  the quota that covers your expected number of creators × daily uploads, with room to grow; the form asks you to explain
  the number.
- **Storage and refresh (Developer Policies III.E.4):** answer from `web/youtube_upkeep.py` (CLAUDE.md gotcha 27):
  tokens kept while connected; channel name and picture re-read at least every 7 days; every posted video checked at
  least every 7 days, gone ones forgotten; a vlog link's details read again after 30 days or deleted; analytics numbers
  in memory only, at most 30 days; after a disconnect everything about that channel is deleted within 7 days (14 after a
  removal in Google's settings); account deletion deletes everything at once.
- **Screenshots** of every screen that shows YouTube data: Shorts & Reels, Scheduled, Vlogs, Analytics (each tab), and
  the Posted list. The YouTube branding rules apply: where YouTube data is shown it should be clear it comes from
  YouTube (links say "Open in Studio" / "On YouTube").
- **Same demo video** as above.

---

## 3. Meta: App Review (Advanced Access) and Business Verification

developers.facebook.com → the Pit Crew app. **Start Business Verification first**: it often takes the longest.

**Settings:** Instagram → API setup with Instagram login → Business login settings: OAuth redirect URI
`https://<domain>/api/instagram/callback`; **Deauthorize callback URL**: `https://<domain>/api/instagram/deauthorize`;
**Data deletion request URL**: `https://<domain>/api/instagram/data-deletion` (both answer Meta's signed requests,
`web/instagram_deletion.py`). Data deletion instructions, if a form asks for a page: `https://<domain>/data-deletion`. App settings → Basic: privacy policy `https://<domain>/privacy`, terms
`https://<domain>/terms`, app icon, category "Business and pages" (or the closest).

**Permissions to request (Advanced Access)**, with the "how will your app use this" text:

`instagram_business_basic`:
> When a creator connects their Instagram professional account, Pit Crew reads the account's ID, username, account type
> and profile picture, so it can show which account is connected, check it's a Business or Creator account (only those
> can be posted to), and let the creator switch between their connected accounts.

`instagram_business_content_publish`:
> Pit Crew turns the creator's long vlog into short vertical clips. When the creator chooses a clip, writes or accepts its
> caption and picks a time, Pit Crew publishes it to their account as a Reel at that time (media container with
> video_url, then media_publish). Nothing is ever posted without the creator choosing the clip, caption and time.

`instagram_business_manage_insights`:
> Pit Crew's Analytics page shows the creator how the Reels it posted for them are doing (views, reach, likes, comments,
> shares, saves) next to the same clips on YouTube, and their account's audience (followers by country, age and city;
> follower changes after each Reel). Only that creator sees it. Pit Crew saves each of its own Reels' totals once a day so
> it can show the first week's numbers; other numbers are kept in memory for minutes.

**Screencast per permission** (Meta wants one for each, about 1–2 minutes, with English captions or narration):

1. *basic:* sign in to Pit Crew → Channels → **Connect Instagram** → Instagram's login and permission screen → back in
   Pit Crew, the connected account's username and picture.
2. *content_publish:* open a made clip → Instagram tab → caption → choose a time a few minutes ahead → wait → show the
   Reel on the Instagram account (in the app or on instagram.com).
3. *manage_insights:* Analytics → Instagram (Both / Instagram filter) → the Reels' numbers and the audience section.

**Test access for the reviewer:** Meta's reviewers need to sign in. Make a Pit Crew test account for them (an email
you control, added with `deploy/invite.sh`) and give that email and its password only in Meta's private
"reviewer instructions" box, plus the steps: "Sign in → Channels → Connect Instagram → log in with your own Instagram
professional test account". Pit Crew posts only what the reviewer chooses.

After approval, switch the app to **Live** mode. Then any Instagram professional account can connect, without being
added as a tester.
