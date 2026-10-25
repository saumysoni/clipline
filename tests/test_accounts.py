"""Accounts: sign-up, sign-in, sign-out, Google sign-in rules, limits, private beta, sessions (web/accounts.py)."""
from tests import fakes as F

import os
import time
import unittest

from accounts import db


class Base(unittest.TestCase):
    def setUp(self):
        F.install()
        F.reset()
        self.c = F.client()

    def signup(self, email, password="password-123", **extra):
        return self.c.post("/api/auth/signup", json={"email": email, "password": password, **extra})


class SignUp(Base):
    def test_new_account_signs_in_and_sends_confirmation(self):
        email = f"new{time.time_ns()}@Example.com"
        r = self.signup(email, name="Maya")
        self.assertEqual(r.status_code, 200, r.get_json())
        me = self.c.get("/api/me").get_json()["user"]
        self.assertEqual(me["email"], email.lower())
        self.assertFalse(me["verified"])
        F.wait_for_mail(email.lower(), "Confirm")

    def test_bad_input(self):
        for email, pw, field in (("not-an-email", "password-123", "email"), ("a@b.co", "short", "password"),
                                 ("a@b.co", "x" * 201, "password"), ("x" * 199 + "@b.co", "password-123", "email")):
            r = self.signup(email, pw)
            self.assertEqual(r.status_code, 400, (email, pw))
            self.assertEqual(r.get_json()["field"], field)

    def test_email_taken(self):
        u = F.new_user()
        r = self.signup(u["email"].upper())
        self.assertEqual(r.status_code, 400)
        self.assertIn("Sign in instead", r.get_json()["error"])

    def test_google_only_account_told_to_use_google(self):
        email = f"g{time.time_ns()}@example.com"
        db.create_user(email, "G", google_sub=f"sub{time.time_ns()}")
        r = self.signup(email)
        self.assertIn("through Google", r.get_json()["error"])

    def test_five_new_accounts_per_hour_from_one_place(self):
        for k in range(5):
            self.assertEqual(self.signup(f"burst{k}{time.time_ns()}@example.com").status_code, 200)
        r = self.signup(f"burst6{time.time_ns()}@example.com")
        self.assertEqual(r.status_code, 429)

    def test_private_beta(self):
        path = os.environ["INVITES_FILE"]
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "w").write("invited@example.com\n")
        os.environ["INVITE_ONLY"] = "1"
        try:
            r = self.signup("stranger@example.com")
            self.assertEqual(r.status_code, 403)
            self.assertIn("private beta", r.get_json()["error"])
            self.assertEqual(self.signup("invited@example.com").status_code, 200)
        finally:
            os.environ["INVITE_ONLY"] = ""


class SignIn(Base):
    def test_right_and_wrong_password(self):
        u = F.new_user(password="right-password")
        r = self.c.post("/api/auth/login", json={"email": u["email"], "password": "wrong-password"})
        self.assertEqual(r.status_code, 400)
        self.assertIsNone(self.c.get("/api/me").get_json()["user"])
        r = self.c.post("/api/auth/login", json={"email": " " + u["email"].upper(), "password": "right-password"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.c.get("/api/me").get_json()["user"]["email"], u["email"])

    def test_ten_wrong_tries_lock_for_15_minutes(self):
        u = F.new_user(password="right-password")
        for _ in range(10):
            self.c.post("/api/auth/login", json={"email": u["email"], "password": "nope-nope"})
        r = self.c.post("/api/auth/login", json={"email": u["email"], "password": "right-password"})
        self.assertEqual(r.status_code, 429)

    def test_unknown_email_same_answer(self):
        r = self.c.post("/api/auth/login", json={"email": "nobody@example.com", "password": "whatever-1"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("Wrong email or password", r.get_json()["error"])

    def test_logout(self):
        c = F.client(F.new_user())
        self.assertIsNotNone(c.get("/api/me").get_json()["user"])
        c.post("/api/auth/logout")
        self.assertIsNone(c.get("/api/me").get_json()["user"])
        self.assertEqual(c.get("/api/vlogs").status_code, 401)

    def test_bumped_session_version_signs_out_everywhere(self):
        u = F.new_user()
        c = F.client(u)
        with db.connect() as con:
            con.execute("UPDATE users SET session_version = session_version + 1 WHERE id = ?", (u["id"],))
        self.assertEqual(c.get("/api/vlogs").status_code, 401)


class GoogleUser(Base):
    def test_rules(self):
        from web.accounts import EMAIL_EXISTS, google_user
        sub = f"sub{time.time_ns()}"
        info = {"sub": sub, "email": f"{sub}@gmail.com", "name": "G", "email_verified": True}
        first = google_user(info)
        self.assertEqual(google_user(info)["id"], first["id"])  # same Google account, same user
        pw = F.new_user()
        with self.assertRaises(RuntimeError) as e:  # an email with a password account is never joined
            google_user({**info, "sub": sub + "x", "email": pw["email"]})
        self.assertEqual(str(e.exception), EMAIL_EXISTS)
        self.assertTrue(db.user_by_id(first["id"])["email_verified"])


class Gate(Base):
    def test_every_api_route_needs_sign_in(self):
        from web.accounts import PUBLIC
        from web.server import app
        open_ok = 0
        for rule in app.url_map.iter_rules():
            if rule.endpoint in PUBLIC or rule.endpoint == "static":
                continue
            url = rule.rule.replace("<job_id>", "abcdef0123").replace("<int:idx>", "1").replace("<path:name>", "x.jpg") \
                .replace("<upload_id>", "0" * 32).replace("<video_id>", "vid").replace("<token>", "t")
            for m in sorted(rule.methods - {"HEAD", "OPTIONS"}):
                r = self.c.open(url, method=m, json={})
                self.assertEqual(r.status_code, 401, f"{m} {url} answered {r.status_code} signed out")
                open_ok += 1
        self.assertGreater(open_ok, 60)

    def test_cross_site_post_refused(self):
        c = F.client(F.new_user())
        r = c.post("/api/auth/logout", headers={"Origin": "https://evil.example"})
        self.assertEqual(r.status_code, 403)
        r = c.post("/api/auth/logout", headers={"Origin": "http://localhost"})
        self.assertEqual(r.status_code, 200)

    def test_someone_elses_vlog_is_not_found(self):
        a, b = F.new_user(), F.new_user()
        ca, cb = F.client(a), F.client(b)
        jid, _ = F.make_shorts(ca, 60, 1)
        for m, url in (("GET", f"/api/status/{jid}"), ("POST", f"/api/schedule/{jid}"), ("POST", f"/api/vlogs/{jid}/stop"),
                       ("POST", f"/api/vlogs/{jid}/delete-video"), ("GET", f"/media/{jid}/thumb_1.jpg"),
                       ("POST", f"/api/hooks/{jid}/1"), ("POST", f"/api/retry/{jid}/1"), ("POST", f"/api/look/{jid}/1"),
                       ("GET", f"/api/clips/{jid}/1/post-text"), ("POST", f"/api/instagram/schedule/{jid}")):
            r = cb.open(url, method=m, json={})
            self.assertEqual(r.status_code, 404, f"{m} {url} -> {r.status_code}")
        self.assertEqual(ca.get(f"/api/status/{jid}").status_code, 200)
        r = cb.post("/api/vlogs/delete-videos", json={"ids": [jid]})
        self.assertEqual(r.get_json()["deleted"], [])
        self.assertEqual(ca.get(f"/media/{jid}/thumb_1.jpg").status_code, 200)


if __name__ == "__main__":
    unittest.main()
