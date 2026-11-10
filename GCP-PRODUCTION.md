# Pit Crew on Google Cloud (the beta server, November 2026)

This file covers how Pit Crew runs live for testers on Google Cloud's free trial, how to ship changes to it, and how to
move it later. **LAUNCH.md** is the full launch guide written for Oracle's free server. Most of it applies here too
(settings, Google and Meta consoles, invites, going public). This file only covers what's different on Google Cloud.

**Live site:** https://pitcrew-beta.duckdns.org (a free DuckDNS name until we buy a domain).

---

## What's running, and what it costs

| Thing on Google Cloud | Name | Notes |
|---|---|---|
| Virtual machine | `pitcrew`, zone `us-central1-a` | `e2-standard-4` (4 vCPU, 16 GB), Ubuntu 24.04, 100 GB disk (`pd-balanced`) |
| Fixed public IP | `pitcrew-ip` (region `us-central1`) | The DuckDNS name points at it. It costs a little only while the VM is stopped |
| Firewall rule | `pitcrew-web` | Opens ports 80 and 443 to machines tagged `pitcrew-web` (Caddy needs both for https) |

The **OAuth client** (Google sign-in, Connect YouTube) is still in the older Google Cloud project `golazo-wc2026`, not
the trial project. The app stays in **Testing**, so only Google accounts added as test users can connect YouTube.

**Cost:** everything comes out of the **$300 free-trial credit**. The card is never charged unless someone presses
**Upgrade** in the billing console. The trial ends after **90 days or when the $300 is used up** (about 75-80 days at
this size), and then the VM stops. **Move off by about 15 January 2027** (the trial ends 4 February 2027). Set a budget
alert in Billing → Budgets & alerts ($300, with alerts at $100 / $200 / $250).

On the server, the layout is the same as LAUNCH.md describes:
- the code is in `/opt/pitcrew/app` (read-only for the app),
- the data is in `/srv/pitcrew` (database, jobs, speech model, backups),
- the settings are in `/opt/pitcrew/app/.env`,
- the service is `pitcrew` (Waitress) behind Caddy (https).

---

## Logging in to the server

On the Mac (the gcloud profile `pitcrew` points at the trial account and project):

```bash
CLOUDSDK_ACTIVE_CONFIG_NAME=pitcrew gcloud compute ssh pitcrew --zone=us-central1-a
```

To run a single command without staying logged in, add `--command='...'`, for example
`--command='sudo bash /opt/pitcrew/app/deploy/status.sh'`.

---

## Everyday jobs

| To... | Do (on the server) |
|---|---|
| **Invite a tester** | `sudo bash /opt/pitcrew/app/deploy/invite.sh friend@example.com "their name"`. Then add the same address as a **test user** in Google Cloud (project `golazo-wc2026` → Google Auth Platform → Audience → Test users), or they can't connect YouTube. If they use Instagram, add them as an Instagram tester in the Meta app too. |
| **See who's invited** | `sudo bash /opt/pitcrew/app/deploy/invite.sh --list` |
| **See how it's doing** | `sudo bash /opt/pitcrew/app/deploy/status.sh` |
| **Change a setting** | `sudo nano /opt/pitcrew/app/.env`, then `sudo systemctl restart pitcrew`. Vlogs being made are queued again. |
| **Read the logs** | `sudo journalctl -u pitcrew -n 100 --no-pager` (Pit Crew), `sudo journalctl -u caddy -n 50 --no-pager` (https) |
| **Copy the backups to the Mac** | On the Mac: `CLOUDSDK_ACTIVE_CONFIG_NAME=pitcrew gcloud compute scp --recurse pitcrew:/srv/pitcrew/backups ~/pitcrew-backups --zone=us-central1-a` |

Testers invited so far: Nesh (2 addresses), Saumya (2 addresses), the Pit Crew helpdesk address.

---

## Shipping a change (any new feature or fix)

The server never gets code by hand. It only takes what's on `main` on GitHub.

1. Work on your own branch (`nesh` or `saumya`) and run the tests on your Mac (CLAUDE.md, "Testing").
2. Commit, push, and open a pull request into `main`. The other person looks at it, then merges it on GitHub.
3. Update the server at a quiet time, when no vlog is being made:
   ```bash
   CLOUDSDK_ACTIVE_CONFIG_NAME=pitcrew gcloud compute ssh pitcrew --zone=us-central1-a
   sudo bash /opt/pitcrew/app/deploy/update.sh
   ```
   `update.sh` does these steps:
   - backs up the database,
   - pulls `main`,
   - installs any new packages from `requirements.txt`,
   - runs the fast tests,
   - restarts the service.

   If a test fails or the new version doesn't start, it goes back to the old version by itself. Then fix the problem
   on your branch and repeat.
4. Open the site and try what changed. Pages are served with `no-cache`, so a normal reload gets the new files.

**If a change needs a new setting:** add it to `.env.example` as usual. `update.sh` does **not** add it to the server's
`.env`, so after updating, add it with `sudo nano /opt/pitcrew/app/.env` and restart.

**If the change touches `editor-app/`:** rebuild and commit `static/editor-app/` before the pull request. The server
has no Node, so it can't build it.

---

## Turning on Instagram (when the Instagram pipeline is ready)

The code arrives the usual way (above). Instagram also needs these steps once:

1. In the Meta app (developers.facebook.com → your app → Instagram → API setup with Instagram login):
   - **Redirect URL:** `https://pitcrew-beta.duckdns.org/api/instagram/callback`
   - **Deauthorize callback URL:** `https://pitcrew-beta.duckdns.org/api/instagram/deauthorize`
   - **Data deletion request URL:** `https://pitcrew-beta.duckdns.org/api/instagram/data-deletion`
   - Add each tester's Instagram account under **Roles → Instagram testers**. They accept the invite in Instagram
     (Settings → Apps and websites → Tester invites).
2. On the server, put the app's keys in `.env`:
   ```
   INSTAGRAM_APP_ID=...
   INSTAGRAM_APP_SECRET=...
   ```
   `INSTAGRAM_REDIRECT_URI` and `PUBLIC_URL` were already filled in by the setup. Then run
   `sudo systemctl restart pitcrew`.
3. Connect an Instagram professional account in Pit Crew and post one Reel to check it. Instagram downloads each
   Reel from `PUBLIC_URL`, so the site must be reachable over https (it is).

Never paste the app secret into chat or commit it.

---

## When we buy a domain

1. At the domain seller, add an **A record** for the domain pointing at the server's IP
   (`gcloud compute addresses describe pitcrew-ip --region=us-central1 --format='value(address)'`).
2. On the server, run the setup again with the new domain. It updates Caddy and gets a certificate:
   ```bash
   sudo bash /opt/pitcrew/app/deploy/setup.sh newdomain.com you@example.com
   ```
3. **The setup keeps the addresses already in `.env`**, so change these four by hand, then restart:
   ```
   APP_URL=https://newdomain.com
   PUBLIC_URL=https://newdomain.com
   YOUTUBE_REDIRECT_URI=https://newdomain.com/api/youtube/callback
   INSTAGRAM_REDIRECT_URI=https://newdomain.com/api/instagram/callback
   ```
4. Add the new addresses in Google Cloud (OAuth client → Authorized redirect URIs and JavaScript origins, Branding →
   homepage, privacy and terms links, which are on nr1306.github.io for now). Do the same in the Meta app (the three
   URLs above).
5. Move email to the domain's own address (it sends from a personal Gmail for now). This is in LAUNCH.md section 5.

---

## Moving to the Oracle server (before the trial ends)

1. Make the Oracle server and run its setup (LAUNCH.md sections 2-4).
2. Stop Pit Crew on Google Cloud so nothing changes while copying: `sudo systemctl stop pitcrew`.
3. Copy **all of `/srv/pitcrew`** and the **`.env`** across. The nightly backups leave out the jobs and `.env`, and
   `.env` holds `TOKEN_KEY`: without it, every saved YouTube and Instagram connection can't be read.
4. Point the domain (or DuckDNS) at the Oracle IP, start Pit Crew there, and check that sign-in, a vlog and a
   connection work.
5. Then delete the Google Cloud resources so nothing is left running:
   ```bash
   CLOUDSDK_ACTIVE_CONFIG_NAME=pitcrew gcloud compute instances delete pitcrew --zone=us-central1-a
   CLOUDSDK_ACTIVE_CONFIG_NAME=pitcrew gcloud compute addresses delete pitcrew-ip --region=us-central1
   CLOUDSDK_ACTIVE_CONFIG_NAME=pitcrew gcloud compute firewall-rules delete pitcrew-web
   ```
   Also delete the `pitcrew-retry` machine on Oracle that was hunting for the free server.

---

## If something goes wrong

LAUNCH.md's "If something goes wrong" table applies here too. Two things differ on Google Cloud:
- **The site doesn't open at all:** check the firewall rule `pitcrew-web` exists and the VM still has the tag
  `pitcrew-web`. There's no extra iptables block on Google's Ubuntu image, unlike Oracle's.
- **Everything stopped one day:** the trial probably ended or the credit ran out. Check
  console.cloud.google.com/billing.
