"""
System tests of the real server process (serve.py's Waitress setup, tests/system/fake_server.py) over real HTTP:
pages, cookies, sign-up and sign-in, sending a 20 MB video in pieces, making Shorts, request limits, and what happens
when the process is killed in the middle of a vlog and started again.

    python -m unittest discover -s tests/system -t . -p "system_*.py"
"""
from tests import _env  # noqa: F401  (first: clean settings)

import http.cookiejar
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class Server:
    """One fake_server process. env: extra settings. Keeps the same data folder across restarts."""

    def __init__(self, data=None, **env):
        self.port, self.env, self.data = free_port(), env, data

    def start(self):
        env = {**os.environ, "PITCREW_TEST_PORT": str(self.port), "PYTHONDONTWRITEBYTECODE": "1", **self.env}
        if self.data:
            env.update(DATABASE_PATH=str(self.data / "data" / "test.db"), JOBS_DIR=str(self.data / "jobs"),
                       PITCREW_KEEP_DIRS="1")
        self.proc = subprocess.Popen([sys.executable, "-m", "tests.system.fake_server"], cwd=ROOT, env=env,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        end = time.time() + 60
        while time.time() < end:
            line = self.proc.stdout.readline()
            if line.startswith("READY"):
                self.data = self.data or Path(line.split()[2])
                # keep reading what it prints, or the pipe fills up and the server freezes on its next print
                self.log = []
                threading.Thread(target=lambda: [self.log.append(x) for x in self.proc.stdout], daemon=True).start()
                return self
            if not line and self.proc.poll() is not None:
                raise RuntimeError("the server didn't start")
        raise RuntimeError("the server didn't answer in 60 s")

    def stop(self, kill=False):
        self.proc.send_signal(signal.SIGKILL if kill else signal.SIGTERM)
        self.proc.wait(10)

    def url(self, path):
        return f"http://127.0.0.1:{self.port}{path}"


class Browser:
    """A cookie-keeping client, like the page in a browser."""

    def __init__(self, server):
        self.s = server
        self.jar = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def req(self, method, path, body=None, headers=None, raw=False):
        data = body if isinstance(body, (bytes, type(None))) else json.dumps(body).encode()
        h = {"Content-Type": "application/json"} if data is not None and not isinstance(body, bytes) else {}
        r = urllib.request.Request(self.s.url(path), data=data, method=method, headers={**h, **(headers or {})})
        try:
            with self.op.open(r, timeout=60) as resp:
                out = resp.read()
                return resp.status, (out if raw else json.loads(out or b"null")), resp.headers
        except urllib.error.HTTPError as e:
            out = e.read()
            try:
                return e.code, json.loads(out), e.headers
            except ValueError:
                return e.code, out, e.headers

    def form(self, path, fields):
        import urllib.parse
        return self.req("POST", path, urllib.parse.urlencode(fields).encode(),
                        {"Content-Type": "application/x-www-form-urlencoded"})

    def signup(self, email=None):
        email = email or f"s{time.time_ns()}@example.com"
        code, j, _ = self.req("POST", "/api/auth/signup", {"email": email, "password": "password-123"})
        assert code == 200, j
        return email

    def send_video(self, data, piece=8 * 1024 * 1024):
        _, j, _ = self.req("POST", "/api/upload/new", {"name": "vlog.mp4", "size": len(data)})
        uid, off = j["id"], 0
        while off < len(data):
            code, j, _ = self.req("POST", f"/api/upload/{uid}?offset={off}", data[off:off + piece],
                                  {"Content-Type": "application/octet-stream"})
            assert code == 200, j
            off = j["received"]
        return uid

    def wait_status(self, jid, want=("ready", "error"), timeout=120):
        end = time.time() + timeout
        while time.time() < end:
            code, j, _ = self.req("GET", f"/api/status/{jid}")
            if code == 200 and j["status"] in want:
                return j
            time.sleep(0.2)
        raise AssertionError(f"vlog {jid} never reached {want}")


class RealServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = Server().start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.stop()

    def test_pages_and_health(self):
        b = Browser(self.srv)
        for path in ("/", "/welcome", "/privacy", "/terms", "/data-deletion", "/healthz", "/static/js/core.js"):
            code, _, h = b.req("GET", path, raw=True)
            self.assertEqual(code, 200, path)
            self.assertNotIn("Server", h)  # no "Server: waitress"
        code, j, _ = b.req("GET", "/api/vlogs")
        self.assertEqual(code, 401)

    def test_sign_up_cookie_and_cross_site(self):
        b = Browser(self.srv)
        b.signup()
        cookie = next(c for c in b.jar)
        self.assertTrue(cookie.has_nonstandard_attr("HttpOnly"))
        self.assertGreater(cookie.expires - time.time(), 29 * 86400)  # 30-day sign-in
        code, _, _ = b.req("POST", "/api/auth/logout", {}, {"Origin": "https://evil.example"})
        self.assertEqual(code, 403)

    def test_20mb_video_in_pieces_to_shorts(self):
        from tests import fakes as F
        b = Browser(self.srv)
        b.signup()
        data = F.test_video(150).read_bytes() + os.urandom(20 * 1024 * 1024)  # a real video padded to 20 MB+
        uid = b.send_video(data)
        _, st, _ = b.req("GET", f"/api/upload/{uid}")
        self.assertEqual(st["received"], len(data))
        code, j, _ = b.form("/api/start", {"upload": uid, "count": "2"})
        self.assertEqual(code, 200, j)
        st = b.wait_status(j["id"])
        self.assertEqual(st["status"], "ready", st.get("error"))
        code, _, h = b.req("GET", f"/media/{j['id']}/{st['shorts'][0]['thumb']}", raw=True)
        self.assertEqual((code, h["Content-Type"]), (200, "image/jpeg"))

    def test_request_limits(self):
        b = Browser(self.srv)
        b.signup()
        code, j, _ = b.req("POST", "/api/upload/new", {"name": "v.mp4", "size": 100 * 1024 * 1024})
        code, _, _ = b.req("POST", f"/api/upload/{j['id']}?offset=0", os.urandom(66 * 1024 * 1024),
                           {"Content-Type": "application/octet-stream"})
        self.assertEqual(code, 413)  # a piece over Flask's 64 MB is refused, never written


class KilledMidVlog(unittest.TestCase):
    def test_vlog_queued_again_after_a_crash(self):
        from tests import fakes as F
        srv = Server(PITCREW_FAKE_SLOW="4").start()
        b = Browser(srv)
        email = b.signup()
        uid = b.send_video(F.test_video(90).read_bytes())
        _, j, _ = b.form("/api/start", {"upload": uid, "count": "1"})
        jid = j["id"]
        b.wait_status(jid, ("working",))
        time.sleep(1.5)
        srv.stop(kill=True)  # the power goes out mid-transcription
        srv2 = Server(data=srv.data).start()
        try:
            b2 = Browser(srv2)
            code, _, _ = b2.req("POST", "/api/auth/login", {"email": email, "password": "password-123"})
            self.assertEqual(code, 200)
            st = b2.wait_status(jid, timeout=60)
            self.assertEqual(st["status"], "ready", st.get("error"))
            self.assertEqual(st.get("recoveries"), 1)
        finally:
            srv2.stop()
            import shutil
            shutil.rmtree(srv.data, ignore_errors=True)  # the killed server couldn't clean up after itself


if __name__ == "__main__":
    unittest.main()
