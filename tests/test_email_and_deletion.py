"""Email links (confirm email, forgot password) and deleting an account (web/verify_email.py, web/password_reset.py,
web/delete_account.py)."""
from tests import fakes as F

import time
import unittest

from accounts import db
from settings import JOBS_DIR


class Confirm(unittest.TestCase):
    def setUp(self):
        F.install()
        F.reset()

    def test_link_confirms_once(self):
        c = F.client()
        email = f"v{time.time_ns()}@example.com"
        c.post("/api/auth/signup", json={"email": email, "password": "password-123"})
        _, subject, text = F.wait_for_mail(email, "Confirm")
        self.assertIn("https://pitcrew.test/#verify=", text)  # APP_URL, never the request's host
        token = F.link_token(text, "verify")
        other = F.client()  # works signed out, in another browser
        r = other.post("/api/auth/verify", json={"token": token})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(db.user_by_email(email)["email_verified"])
        self.assertEqual(other.post("/api/auth/verify", json={"token": token}).status_code, 400)
        self.assertEqual(other.post("/api/auth/verify", json={"token": "x" * 300}).status_code, 400)

    def test_resend_limit_and_already_confirmed(self):
        u = F.new_user(verified=False)
        c = F.client(u)
        for _ in range(3):
            self.assertEqual(c.post("/api/auth/verify/resend").status_code, 200)
        self.assertEqual(c.post("/api/auth/verify/resend").status_code, 429)
        done = F.client(F.new_user(verified=True)).post("/api/auth/verify/resend").get_json()
        self.assertIn("already confirmed", done["message"])


class Reset(unittest.TestCase):
    def setUp(self):
        F.install()
        F.reset()

    def test_full_reset_ends_old_sessions(self):
        u = F.new_user(password="old-password", verified=False)
        old = F.client(u)
        c = F.client()
        r = c.post("/api/auth/forgot", json={"email": u["email"]})
        self.assertEqual(r.status_code, 200)
        _, _, text = F.wait_for_mail(u["email"], "Reset")
        token = F.link_token(text, "reset")
        self.assertEqual(c.post("/api/auth/reset", json={"token": token, "password": "short"}).status_code, 400)
        r = c.post("/api/auth/reset", json={"token": token, "password": "new-password"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(c.get("/api/me").get_json()["user"]["email"], u["email"])  # signed in
        self.assertTrue(db.user_by_id(u["id"])["email_verified"])  # the link proves the email
        self.assertEqual(old.get("/api/vlogs").status_code, 401)  # every old session ended
        self.assertEqual(c.post("/api/auth/reset", json={"token": token, "password": "another-one"}).status_code, 400)
        r = F.client().post("/api/auth/login", json={"email": u["email"], "password": "new-password"})
        self.assertEqual(r.status_code, 200)

    def test_same_answer_for_unknown_email_and_no_flood(self):
        c = F.client()
        a = c.post("/api/auth/forgot", json={"email": "nobody@example.com"}).get_json()
        u = F.new_user()
        b = c.post("/api/auth/forgot", json={"email": u["email"]}).get_json()
        self.assertEqual(a, b)
        for _ in range(5):
            c.post("/api/auth/forgot", json={"email": u["email"]})
        time.sleep(0.3)
        self.assertEqual(len([m for m in F.OUTBOX if m[0] == u["email"]]), 3)
        self.assertEqual(c.post("/api/auth/forgot", json={"email": "bad"}).status_code, 400)

    def test_expired_link(self):
        u = F.new_user()
        token = db.new_password_reset(u["id"])
        with db.connect() as con:
            con.execute("UPDATE password_resets SET expires_at = ?", (time.time() - 1,))
        r = F.client().post("/api/auth/reset", json={"token": token, "password": "new-password"})
        self.assertEqual(r.status_code, 400)
        self.assertTrue(r.get_json()["expired"])


class DeleteAccount(unittest.TestCase):
    def setUp(self):
        F.install()
        F.reset()

    def test_everything_goes(self):
        u = F.new_user()
        c = F.client(u)
        jid, _ = F.make_shorts(c, 60, 2)
        F.connect_youtube(u["id"])
        F.connect_instagram(u["id"])
        db.save_reel_snapshot(u["id"], "M1", "2026-10-01", {"views": 1})
        unfinished = c.post("/api/upload/new", json={"name": "next.mp4", "size": 1000}).get_json()["id"]
        r = c.post("/api/account/delete", json={"email": "wrong@example.com"})
        self.assertEqual(r.status_code, 400)
        r = c.post("/api/account/delete", json={"email": u["email"].upper()})
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertIsNone(db.user_by_id(u["id"]))
        self.assertFalse((JOBS_DIR / jid).exists())
        self.assertFalse((JOBS_DIR / "_uploads" / unfinished).exists())
        self.assertIn("UCchannel000000000000001", F.REVOKED)  # YouTube access revoked at Google
        self.assertEqual(db.connections(u["id"], "instagram"), [])
        self.assertEqual(db.reel_snapshots(u["id"], ["M1"])["M1"], [])
        self.assertIsNone(c.get("/api/me").get_json()["user"])

    def test_refused_while_working(self):
        u = F.new_user()
        c = F.client(u)
        F.SLOW.transcribe = 3
        up = F.upload(c, F.test_video(60))
        jid = c.post("/api/start", data={"count": "1", "upload": up}).get_json()["id"]
        F.wait(lambda: F.job_json(jid).get("stage") == 1, what="transcribing")
        r = c.post("/api/account/delete", json={"email": u["email"]})
        self.assertEqual(r.status_code, 400)
        self.assertIn("still working", r.get_json()["error"])
        c.post(f"/api/vlogs/{jid}/stop")
        F.SLOW.transcribe = 0
        F.wait(lambda: not (JOBS_DIR / jid).exists(), what="stopped vlog removed")
        self.assertEqual(c.post("/api/account/delete", json={"email": u["email"]}).status_code, 200)

    def test_shared_transcripts_of_other_people_stay(self):
        a, b = F.new_user(), F.new_user()
        ca, cb = F.client(a), F.client(b)
        F.make_shorts(ca, 60, 1)
        F.make_shorts(cb, 90, 1)
        from pipeline.transcript_cache import TRANSCRIPTS_DIR
        before = set(TRANSCRIPTS_DIR.glob("*.json"))
        self.assertGreaterEqual(len(before), 2)
        ca.post("/api/account/delete", json={"email": a["email"]})
        after = set(TRANSCRIPTS_DIR.glob("*.json"))
        self.assertEqual(len(before - after), 1)  # only a's video's transcript


if __name__ == "__main__":
    unittest.main()
