# Launching Pit Crew (private beta on Oracle Cloud's free server)

Step by step, from nothing to Pit Crew running at `https://<your-domain>` for you and invited testers. Plan on an
afternoon; most of it is waiting for sign-ups and DNS. Facts here were checked in October 2026; the consoles change their
buttons now and then, so if a name differs, look for the nearest match.

**What the beta is:** Pit Crew on the internet, for up to about 100 people you invite. Until Google and Meta approve
the app (section 10), YouTube uploads from Pit Crew stay **private** (you make them public in YouTube Studio), and only
people you add as testers can connect YouTube and Instagram.

**What it costs:** $0 (Oracle's Always Free server, a free student domain for the first year, Gmail for email).

---

## 1. Get a domain (free with the GitHub Student Developer Pack)

1. Open https://education.github.com/pack (signed in to GitHub with your student status approved).
2. Take one free domain: **Namecheap** gives a `.me` for a year, **Name.com** one from a list (`.app`, `.dev`, ...), or
   **.TECH** a `.tech`. Something short, e.g. `pitcrew.me` or `getpitcrew.app` (whatever is free).
3. Note when the free year ends: renewing is about $10–20 a year.

Leave the DNS settings for now (step 3).

## 2. Make the free server on Oracle Cloud

1. Sign up at https://www.oracle.com/cloud/free/. Choose your **home region** carefully (it can't be changed): the one
   nearest most of your viewers' creators, e.g. India South (Hyderabad) or US East (Ashburn). A card is asked for to
   prove who you are; Always Free resources aren't charged.
2. **Make an SSH key** on your Mac (skip if you have `~/.ssh/id_ed25519.pub`):
   ```bash
   ssh-keygen -t ed25519 -C "pitcrew-server"
   cat ~/.ssh/id_ed25519.pub     # you'll paste this into Oracle
   ```
3. In the Oracle console: **Compute → Instances → Create instance**.
   - **Name:** `pitcrew`
   - **Image:** Canonical **Ubuntu 24.04** (not "Minimal", not Oracle Linux)
   - **Shape:** Ampere → **VM.Standard.A1.Flex**, **2 OCPUs, 12 GB memory** (the whole free allowance)
   - **Networking:** keep "Create new virtual cloud network" and **Assign a public IPv4 address**
   - **SSH keys:** "Paste public key", paste the line from step 2
   - **Boot volume:** "Specify a custom size": **100 GB** (free up to 200 GB in total)
   - **Create.** If it says **"Out of capacity"**, free Arm servers are busy in that zone: try another
     "Availability domain" on the same page, or try again later (early morning often works).
4. Keep the server's address the same forever: open the instance → **Attached VNICs** → the VNIC → **IPv4 Addresses** →
   edit the address → **Reserved public IP** → create one. Note the IP (e.g. `141.148.x.x`).
5. **Open the web ports:** on the instance page click the **Subnet** → **Security** (Security Lists) → the default list →
   **Add Ingress Rules**, twice: Source CIDR `0.0.0.0/0`, IP protocol TCP, destination port `80`; then the same with `443`.
   (The setup script opens them inside the server too: Oracle's Ubuntu blocks them twice.)
6. Log in once to check: `ssh ubuntu@<server-ip>` (type `yes` the first time).

**Oracle can reclaim idle free servers.** If, over 7 days, the server's CPU, network *and* memory use all stay under 20%,
Oracle may reclaim it ([Oracle's rule](https://docs.oracle.com/en-us/iaas/Content/FreeTier/resourceref.htm)). A quiet
beta can look like that. Two honest options:
- **Upgrade the account to "Pay As You Go"** (Billing → Upgrade). Always Free resources stay free, and people report
  idle reclaiming doesn't happen on paid accounts (Oracle's page doesn't say either way). Set a **budget alert at $1**
  (Billing → Budgets) so any charge would email you at once. Recommended once the beta has real users.
- **Stay free** and accept the risk while it's only you and a few testers. Either way, copy the backups to your Mac
  every week (section 8), so a reclaimed server costs an evening, not your data.

## 3. Point the domain at the server

In your domain company's DNS settings (Namecheap: Domain List → Manage → **Advanced DNS**):
- Delete any existing "parking" A or CNAME records for `@`.
- Add an **A record**: Host `@`, Value `<server-ip>`, TTL automatic.

Check it from your Mac after a few minutes (can take up to an hour): `dig +short <your-domain>` should print the server IP.

## 4. Run the setup on the server

```bash
ssh ubuntu@<server-ip>
git clone https://github.com/saumysoni/clipline.git
sudo bash clipline/deploy/setup.sh <your-domain> <your-email>
```

It takes 10–20 minutes (it installs FFmpeg, Python packages and the speech model) and ends with **"Done. Pit Crew is
running."** and a list of settings still to fill in. What it set up, so you know where things are:

| What | Where |
|---|---|
| The code (branch `main`) | `/opt/pitcrew/app` (read-only for Pit Crew) |
| Settings and secrets | `/opt/pitcrew/app/.env` |
| Accounts database, invite list | `/srv/pitcrew/data/` |
| Vlogs and clips | `/srv/pitcrew/jobs/` |
| Nightly database backups (14 days) | `/srv/pitcrew/backups/` |
| The service | `sudo systemctl status pitcrew` · logs: `sudo journalctl -u pitcrew -f` |
| https (Caddy, renews the certificate by itself) | `/etc/caddy/Caddyfile` |

Open `https://<your-domain>/welcome`: you should see Pit Crew's homepage with a padlock.

## 5. Fill in the settings

```bash
sudo nano /opt/pitcrew/app/.env
```
Copy these from your Mac's `.env` and `client_secret.json` (never commit or paste them anywhere public):

| Setting | Where it comes from |
|---|---|
| `GEMINI_API_KEY` | Your Gemini key (Google AI Studio) |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | In `client_secret.json`: `client_id` and `client_secret` |
| `INSTAGRAM_APP_ID`, `INSTAGRAM_APP_SECRET` | Meta app → Instagram → API setup with Instagram login |
| `SUPPORT_EMAIL` | The address testers write to (shown on Help, emails and the privacy policy): `neshrochwani121@gmail.com`, as on the old pages |
| `OPERATOR_NAME` | Who runs Pit Crew, as it should appear on the privacy policy, e.g. `Saumya Soni and Nesh <surname>` |
| `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`, `SMTP_USER`, `SMTP_PASSWORD`, `MAIL_FROM` | A Gmail account with 2-step verification and an **app password** (Google Account → Security → App passwords). `MAIL_FROM` e.g. `Pit Crew <you@gmail.com>` |

**Don't copy** `SECRET_KEY`, `TOKEN_KEY` or `DATABASE_PATH` from your Mac: the server made its own. The server starts
with no accounts or vlogs (your Mac's stay on your Mac).

Then: `sudo systemctl restart pitcrew`.

**Keep a copy of the server's `.env` somewhere safe that isn't the server** (a password manager): it holds `TOKEN_KEY`,
without which every YouTube and Instagram connection has to be made again. Print it with `sudo cat /opt/pitcrew/app/.env`.

## 6. Tell Google and Meta about the new address

**Google Cloud** (https://console.cloud.google.com, the project you already use):
1. **APIs & Services → Credentials →** your OAuth client → **Authorized redirect URIs → Add**:
   `https://<your-domain>/api/youtube/callback` (keep the localhost one for your Mac). **Authorized JavaScript origins → Add**:
   `https://<your-domain>`. Save.
2. **OAuth consent screen** (Google Auth Platform → Branding): App home page `https://<your-domain>/welcome`, Privacy
   policy `https://<your-domain>/privacy`, Terms of service `https://<your-domain>/terms`, **Authorized domains**:
   `<your-domain>`. Keep the app in **Testing** for now.
3. **Audience → Test users → Add users:** your own Google address, and each tester's (up to 100). Only test users can
   connect YouTube while the app is in Testing. (In Testing, a YouTube connection expires after about a week:
   reconnecting fixes it. That ends with verification, section 10.)

**Meta** (https://developers.facebook.com/apps → your app):
1. **Instagram → API setup with Instagram login → Set up Instagram business login → Business login settings →
   OAuth redirect URIs:** add `https://<your-domain>/api/instagram/callback`. Save.
2. Same page: **Deauthorize callback URL**: `https://<your-domain>/api/instagram/deauthorize`; **Data deletion request
   URL**: `https://<your-domain>/api/instagram/data-deletion` (Meta calls both; `web/instagram_deletion.py`).
3. **App settings → Basic:** Privacy policy URL `https://<your-domain>/privacy`, Terms of service URL
   `https://<your-domain>/terms`, App domains `<your-domain>`. Save.
4. **App roles → Roles → Instagram testers → Add:** each tester's Instagram username. They accept it in the Instagram
   app (Settings → Website permissions → Apps and websites → Tester invites).

## 7. Try it yourself first

1. Invite yourself: `sudo bash /opt/pitcrew/app/deploy/invite.sh <your-email>`
2. Open `https://<your-domain>`, **Create an account** (or Continue with Google), confirm your email from the message.
3. **Connect YouTube** and **Connect Instagram** in the sidebar.
4. Make Shorts from a **short test vlog** (90 seconds is enough: `ffmpeg -ss 300 -i long.mp4 -t 90 -c copy test90.mp4`).
   Time how long it takes; transcription runs on the server's 2 processor cores, so it's slower than your Mac. The
   first vlog after setup may also wait a minute for the speech model.
5. Post one Short (it goes up private: make it public in YouTube Studio) and one Reel. Check the captions are bold
   Montserrat, the thumbnail looks right, and Analytics opens.
6. `sudo bash /opt/pitcrew/app/deploy/status.sh` should show everything healthy.
7. **Point the old pages at the site.** On your Mac, in the clipline folder on your branch:
   `bash deploy/point-docs.sh <your-domain>`. It turns `docs/` (the old GitHub Pages homepage, privacy policy and terms)
   into redirects to `/welcome`, `/privacy` and `/terms`, but only once the site answers. Commit `docs/` and open a PR.

If anything's off, `sudo journalctl -u pitcrew -n 100 --no-pager` shows what happened; send it to me.

## 8. Running the beta

| To... | Do |
|---|---|
| **Invite a tester** | `sudo bash /opt/pitcrew/app/deploy/invite.sh friend@example.com "their name"`, add them as a **Google test user** (section 6) and, if they use Instagram, as an **Instagram tester**. Tell them to sign up with that email. |
| **Ship a new version** | Merge the pull request into `main` on GitHub, then on the server: `sudo bash /opt/pitcrew/app/deploy/update.sh`. It backs up the database, updates, restarts, and goes back to the old version by itself if the new one doesn't start. |
| **See how it's doing** | `sudo bash /opt/pitcrew/app/deploy/status.sh` |
| **Run the tests on the server** | `sudo bash /opt/pitcrew/app/deploy/test.sh` (fast, ~1 min; `system`, `ab`, `stress` for the longer ones, when few people are using it; `live --url https://<your-domain> --email <a test account>` for a gentle read-only check of the site itself). They never touch the live data or keys. |
| **Copy the backups to your Mac** (weekly) | On your Mac: `scp -r ubuntu@<server-ip>:/srv/pitcrew/backups ~/pitcrew-backups` (the setup lets your login read them; log in again once after setup) |
| **Know when it's down** | Free monitor: https://uptimerobot.com → New monitor → HTTP(s) → `https://<your-domain>/healthz` → alerts to your email. |
| **Change a setting** | `sudo nano /opt/pitcrew/app/.env`, then `sudo systemctl restart pitcrew` (vlogs being made are queued again). |

Never edit code on the server: changes go through GitHub (`saumya` → pull request → `main`) and `update.sh`, which
refuses to run if server files were edited by hand.

**Limits worth knowing during the beta:** YouTube gives the whole app **100 uploads a day** (shared by everyone; the
YouTube audit raises it). Anyone uploads freely until 60 are used, then the rest is shared fairly; anything over
the limit waits in Pit Crew and goes up after midnight Pacific by itself, so creators never see a failure. Each creator gets **600 minutes of vlog a month** and vlogs up to **120 minutes**
(`MONTHLY_VLOG_MINUTES`, `MAX_VLOG_MINUTES` in `.env`). One vlog is made at a time on the free server; others wait their turn.

## 9. Before you invite people beyond yourself and Nesh

- **Gemini's free plan** lets Google use what Pit Crew sends (transcripts, frames) to improve its products. The
  privacy policy says so while `GEMINI_PAID` is empty. For the beta we stay on the free plan (decided Oct 2026), so
  Pit Crew sends nothing from YouTube to Gemini then: no channel numbers (Pit Crew's read on Analytics is written
  without AI) and not a vlog's details read from its YouTube link. When there's budget, turn on billing for the key in
  Google AI Studio, set `GEMINI_PAID=1` in `.env` and restart: the policy and the AI features update themselves.
- **Email:** nobody can use Pit Crew until they click the link in the confirmation email, so SMTP must work before
  you invite anyone (sign up with a test address and check the email arrives, also in spam).
- Read the privacy policy and terms (`/privacy`, `/terms`) once, as the people responsible for them. I wrote them
  from what the code actually does, but I'm not a lawyer.

## 10. Going public (later, after the beta settles)

Each of these is free and done once. All of them need the domain, homepage, privacy policy and terms from this guide.
**REVIEWS.md** has the text to paste into each form and the shot list for each demo video.

1. **Google verification** (so anyone can connect YouTube, without the "unverified app" screen or the 100-user cap):
   verify the domain in Google Search Console, then on the OAuth consent screen **Publish app** and submit for
   verification. You'll need a demo video (unlisted on YouTube) showing the sign-in, the consent screen with the
   app name and client ID in the address bar, and each permission in use. Google says it typically takes 3–5 business days.
2. **YouTube API audit** (uploads can be public, and more than 100 a day): the YouTube API Services Audit and Quota
   Extension form. Pit Crew keeps YouTube's stored-data rules (policy III.E.4: refresh or delete within 30 days, delete
   after a revocation) with a daily check, `web/youtube_upkeep.py`.
3. **Meta app review + business verification** (so any Instagram professional account can connect): request Advanced
   Access for `instagram_business_basic`, `instagram_business_content_publish` and `instagram_business_manage_insights`,
   with a screencast of each in use.
4. Then open sign-ups: empty `INVITE_ONLY` in `.env` and restart.

## If something goes wrong

| What you see | Why, and what to do |
|---|---|
| The site doesn't open at all | DNS not pointing yet (`dig +short <your-domain>`), or ports 80/443 not open in Oracle's Security List (step 2.5). |
| "Your connection is not private" | Caddy couldn't get the certificate: usually DNS or the ports. `sudo journalctl -u caddy -n 50 --no-pager`, fix, then `sudo systemctl restart caddy`. |
| 502 Bad Gateway | Pit Crew isn't running: `sudo journalctl -u pitcrew -n 100 --no-pager`. |
| Google: "redirect_uri_mismatch" | The redirect URI in Google Cloud must be exactly `https://<your-domain>/api/youtube/callback`. |
| Google: "Access blocked: app has not completed verification" | That Google account isn't a test user (section 6). |
| Instagram: "Invalid redirect_uri" | Add `https://<your-domain>/api/instagram/callback` to the Meta app (section 6). |
| "This email isn't on the invite list" | `invite.sh` that exact address (any capitals are fine). |
| No emails arrive | Check the SMTP settings and the Gmail app password; the log says what the mail server answered. |
| A vlog waits a long time | One vlog is made at a time on the free server; the page shows its place in the queue. |
