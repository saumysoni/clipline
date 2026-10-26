"""
Stress tests: many people using Pit Crew at once, measured (how long each kind of request takes, p50 / p95 / slowest,
errors, the server's memory and threads before and after).

  local   (default) a full copy of Pit Crew (tests/system/fake_server.py: the real server process, fake YouTube /
          Instagram / AI, throwaway data) on this machine, pushed hard: USERS people at once sign up, keep the pages
          open (polling like the browser does), send videos in 8 MB pieces and queue vlogs; then it checks every vlog
          finished, nothing failed, answers stayed quick and threads didn't pile up.

              python -m tests.stress.stress                       # 25 people, 60 seconds
              python -m tests.stress.stress --users 60 --seconds 120

  live    the real site, gently: only reads (public pages, /healthz, and the signed-in lists with ONE test account
          you made for this), a few requests a second, and it stops by itself if errors pass 2% or answers get slow.
          It never uploads, makes vlogs, posts or changes anything. Use a test account, never a creator's.

              python -m tests.stress.stress live --url https://pitcrewapp.me --email you+stress@example.com
              (it asks for the password; or set STRESS_PASSWORD)

Exit code 0 when everything passed, 1 otherwise.
"""
import argparse
import getpass
import http.cookiejar
import json
import os
import statistics
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict

LAT = defaultdict(list)  # kind -> seconds
ERRORS = defaultdict(int)  # kind -> count
_L = threading.Lock()


class Client:
    def __init__(self, base, timeout=60):
        self.base, self.timeout = base.rstrip("/"), timeout
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(self, kind, method, path, body=None, ctype=None, ok=(200,)):
        data = body if isinstance(body, (bytes, type(None))) else json.dumps(body).encode()
        headers = {"Content-Type": ctype or "application/json"} if data is not None else {}
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"User-Agent": "PitCrew-stress", **headers})
        t = time.time()
        code, out = 0, b""
        try:
            with self.op.open(req, timeout=self.timeout) as r:
                code, out = r.status, r.read()
        except urllib.error.HTTPError as e:
            code, out = e.code, e.read()
        except OSError:
            code = -1
        with _L:
            LAT[kind].append(time.time() - t)
            if code not in ok:
                ERRORS[kind] += 1
        try:
            return code, json.loads(out or b"null")
        except ValueError:
            return code, None


def report(title):
    print(f"\n{title}")
    print(f"  {'request':18} {'count':>6} {'p50 ms':>8} {'p95 ms':>8} {'max ms':>8} {'errors':>7}")
    worst = 0.0
    for kind in sorted(LAT):
        xs = sorted(LAT[kind])
        p95 = xs[min(len(xs) - 1, int(len(xs) * 0.95))]
        if kind not in ("signup", "sign in"):  # password hashing is meant to take a moment
            worst = max(worst, p95)
        print(f"  {kind:18} {len(xs):6} {statistics.median(xs) * 1000:8.0f} {p95 * 1000:8.0f} {xs[-1] * 1000:8.0f} "
              f"{ERRORS[kind]:7}")
    total = sum(len(v) for v in LAT.values())
    errors = sum(ERRORS.values())
    print(f"  {total} requests, {errors} errors ({100 * errors / max(1, total):.2f}%)")
    return total, errors, worst


def proc_stats(pid):
    out = {}
    try:
        for line in open(f"/proc/{pid}/status"):
            k, _, v = line.partition(":")
            if k in ("VmRSS", "VmHWM", "Threads"):
                out[k] = int(v.split()[0])
    except OSError:
        pass
    return out


# ---------------------------------------------------------------- local ---------------------------------------------

def local(users, seconds, vlogs_each):
    from tests import fakes as F
    from tests.system.system_server import Server
    srv = Server(PITCREW_FAKE_SLOW="1.5").start()  # each vlog takes a moment, so the queue really fills up
    base = srv.url("")
    before = proc_stats(srv.proc.pid)
    video = F.test_video(60).read_bytes()
    stop = time.time() + seconds
    made = []  # (client, job id, owner email, when started)
    failures = []

    def person(k):
        c = Client(base)
        email = f"stress{k}-{time.time_ns()}@example.com"
        code, _ = c.call("signup", "POST", "/api/auth/signup", {"email": email, "password": "password-123"})
        if code != 200:
            failures.append(f"sign-up {k}: {code}")
            return
        code, _ = c.call("confirm email", "POST", "/api/auth/verify", {"token": srv.email_token(email)})
        if code != 200:
            failures.append(f"confirm email {k}: {code}")
            return
        for n in range(vlogs_each):  # send a video in 1 MB pieces (many requests), then queue a vlog
            code, j = c.call("upload new", "POST", "/api/upload/new", {"name": "v.mp4", "size": len(video)})
            if code != 200:
                failures.append(f"upload new {k}: {code} {j}")
                return
            off = 0
            while off < len(video):
                code, r = c.call("upload piece", "POST", f"/api/upload/{j['id']}?offset={off}",
                                 video[off:off + 1024 * 1024], "application/octet-stream")
                if code not in (200, 409):
                    failures.append(f"piece {k}: {code}")
                    return
                off = (r or {}).get("received", off)
            body = urllib.parse.urlencode({"upload": j["id"], "count": "1"}).encode()
            code, r = c.call("start vlog", "POST", "/api/start", body, "application/x-www-form-urlencoded")
            if code == 200:
                with _L:
                    made.append((c, r["id"], email, time.time()))
        while time.time() < stop:  # the page left open: what the browser polls
            for kind, path in (("vlogs list", "/api/vlogs"), ("clips list", "/api/clips"), ("me", "/api/me"),
                               ("allowance", "/api/allowance")):
                c.call(kind, "GET", path)
            for _, jid, owner, _ in list(made):
                if owner == email:
                    c.call("status", "GET", f"/api/status/{jid}")
            time.sleep(0.5)

    def visitor():  # people who aren't signed in, reading the public pages
        c = Client(base)
        while time.time() < stop:
            for path in ("/", "/welcome", "/privacy", "/healthz", "/static/js/core.js"):
                c.call("public page", "GET", path)
            time.sleep(0.2)

    threads = [threading.Thread(target=person, args=(k,)) for k in range(users)]
    threads += [threading.Thread(target=visitor) for _ in range(max(1, users // 5))]
    print(f"Local stress: {users} people + {max(1, users // 5)} visitors for {seconds} s, {vlogs_each} vlog(s) each, "
          f"server pid {srv.proc.pid}")
    t0 = time.time()
    for t in threads:
        t.start()
    peak = before
    while any(t.is_alive() for t in threads):
        s = proc_stats(srv.proc.pid)
        if s.get("VmRSS", 0) > peak.get("VmRSS", 0):
            peak = s
        time.sleep(1)
    print(f"  load phase {time.time() - t0:.0f} s; waiting for every queued vlog to finish...")
    finished, end = {}, time.time() + 600
    while len(finished) < len(made) and time.time() < end:
        for c, jid, _, _ in made:
            if jid not in finished:
                code, j = c.call("status (after)", "GET", f"/api/status/{jid}")
                if code == 200 and j["status"] in ("ready", "error"):
                    finished[jid] = (j["status"], time.time())
        time.sleep(0.5)
    after = proc_stats(srv.proc.pid)
    total, errors, worst = report("Requests:")
    bad = [j for j, (st, _) in finished.items() if st != "ready"]
    ok = True
    print(f"\nVlogs: {len(made)} queued, {sum(1 for v in finished.values() if v[0] == 'ready')} ready, {len(bad)} stopped, "
          f"{len(made) - len(finished)} never finished")
    print(f"Server: memory {before.get('VmRSS', 0) // 1024} MB at start, peak {peak.get('VmRSS', 0) // 1024} MB, "
          f"{after.get('VmRSS', 0) // 1024} MB after; threads {before.get('Threads')} -> {after.get('Threads')}")
    checks = [
        (not failures, f"requests that should never fail failed: {failures[:5]}"),
        (errors <= total * 0.001, f"error rate {errors}/{total}"),
        (len(finished) == len(made) and not bad, "not every vlog finished"),
        # 3 s: the people are simulated on the same machine, so they take CPU from the server they're testing
        (worst < 3.0, f"slowest p95 {worst:.2f} s (over 3 s; sign-up is left out: its password hashing is slow on purpose)"),
        (after.get("Threads", 0) <= before.get("Threads", 0) + 30, "threads kept growing (a leak?)"),
    ]
    code, _ = Client(base).call("health after", "GET", "/healthz")
    checks.append((code == 200, f"/healthz after the load answered {code}"))
    for passed, msg in checks:
        if not passed:
            ok = False
            print("  FAIL:", msg)
    srv.stop()
    print("\nPASSED" if ok else "\nFAILED")
    return ok


# ---------------------------------------------------------------- live ----------------------------------------------

def live(url, email, password, seconds, people):
    """Gentle and read-only: at most `people` x ~2 requests a second, stops early on trouble."""
    base = url.rstrip("/")
    c0 = Client(base, timeout=20)
    code, _ = c0.call("health", "GET", "/healthz")
    if code != 200:
        print(f"{base}/healthz answered {code}; not starting.")
        return False
    signed = None
    if email:
        signed = Client(base, timeout=20)
        code, j = signed.call("sign in", "POST", "/api/auth/login", {"email": email, "password": password})
        if code != 200:
            print(f"Couldn't sign in as {email}: {code} {j}. Use a test account made for this.")
            return False
    stop, halted = time.time() + seconds, []

    def worker(k):
        c = signed if (signed and k % 2 == 0) else Client(base, timeout=20)
        while time.time() < stop and not halted:
            if c is signed:
                for kind, path in (("vlogs list", "/api/vlogs"), ("clips list", "/api/clips"), ("me", "/api/me")):
                    c.call(kind, "GET", path)
            else:
                for path in ("/welcome", "/healthz", "/static/js/core.js"):
                    c.call("public page", "GET", path)
            time.sleep(1.0)

    def guard():
        while time.time() < stop and not halted:
            time.sleep(3)
            with _L:
                total = sum(len(v) for v in LAT.values())
                errors = sum(ERRORS.values())
                recent = sorted(x for v in LAT.values() for x in v[-20:])
            if total > 50 and errors > total * 0.02:
                halted.append(f"error rate {errors}/{total}")
            if recent and recent[int(len(recent) * 0.95) - 1] > 3:
                halted.append("answers got slower than 3 s")
    print(f"Live check of {base}: {people} people for {seconds} s, read-only" + (f", signed in as {email}" if email else ""))
    threads = [threading.Thread(target=worker, args=(k,)) for k in range(people)] + [threading.Thread(target=guard)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    total, errors, worst = report("Requests:")
    if halted:
        print(f"\nStopped early: {halted[0]}. Check `sudo bash /opt/pitcrew/app/deploy/status.sh` on the server.")
    ok = not halted and errors <= total * 0.01 and worst < 1.5
    print("\nPASSED" if ok else "\nFAILED")
    return ok


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", nargs="?", default="local", choices=("local", "live"))
    ap.add_argument("--users", type=int, default=25)
    ap.add_argument("--seconds", type=int, default=60)
    ap.add_argument("--vlogs", type=int, default=1, help="vlogs each person makes (local)")
    ap.add_argument("--url", help="the live site (live)")
    ap.add_argument("--email", help="a test account on the live site (live)")
    a = ap.parse_args()
    if a.mode == "live":
        if not a.url:
            ap.error("live needs --url")
        pw = (os.getenv("STRESS_PASSWORD") or getpass.getpass("Test account password: ")) if a.email else ""
        return 0 if live(a.url, a.email, pw, min(a.seconds, 300), min(a.users, 10)) else 1
    return 0 if local(a.users, a.seconds, a.vlogs) else 1


if __name__ == "__main__":
    sys.exit(main())
