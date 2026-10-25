"""Meta's deauthorize and data deletion callbacks (web/instagram_deletion.py)."""
from tests import _env  # noqa: F401  (first: throwaway folders)

import base64
import hashlib
import hmac
import json
import os
import time
import unittest

os.environ["INSTAGRAM_APP_SECRET"] = "test-secret"  # (after tests/_env.py cleared the real one)

import app as pitcrew  # noqa: E402  (registers every route)
from accounts import db  # noqa: E402
from settings import JOBS_DIR  # noqa: E402
from web.instagram_deletion import parse_signed_request  # noqa: E402
from web.store import JOBS  # noqa: E402


def signed(data, secret="test-secret"):
    payload = base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip("=")
    sig = base64.urlsafe_b64encode(hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest()).decode().rstrip("=")
    return f"{sig}.{payload}"


class SignedRequest(unittest.TestCase):
    def test_good_and_bad(self):
        data = {"algorithm": "HMAC-SHA256", "user_id": "1789", "issued_at": 1}
        self.assertEqual(parse_signed_request(signed(data), "test-secret")["user_id"], "1789")
        self.assertIsNone(parse_signed_request(signed(data, "other"), "test-secret"))
        self.assertIsNone(parse_signed_request(signed({**data, "algorithm": "none"}), "test-secret"))
        self.assertIsNone(parse_signed_request("garbage", "test-secret"))
        self.assertIsNone(parse_signed_request(signed(data, ""), ""))


class Callbacks(unittest.TestCase):
    def setUp(self):
        db.init()
        self.client = pitcrew.app.test_client()
        self.uid = db.create_user(f"ig{time.time_ns()}@example.com")
        self.ig = str(time.time_ns())
        db.save_connection(self.uid, "instagram", self.ig, {"token": "t", "ig_id": self.ig}, {"username": "me"})
        db.save_connection(self.uid, "instagram", "keep" + self.ig, {"token": "t"}, {"username": "other"})
        self.jid = format(time.time_ns() % (16 ** 10), "010x")
        (JOBS_DIR / self.jid).mkdir(parents=True)
        (JOBS_DIR / self.jid / "job.json").write_text(json.dumps({
            "id": self.jid, "owner": self.uid, "status": "done", "shorts": [{"idx": 1, "video": "s1.mp4"}],
            "ig_posts": [{"idx": 1, "ig_id": self.ig, "status": "done", "media_id": "m1" + self.ig},
                         {"idx": 2, "ig_id": "keep" + self.ig, "status": "done", "media_id": "m2" + self.ig}]}))
        JOBS.pop(self.jid, None)
        db.save_reel_snapshot(self.uid, "m1" + self.ig, "2026-10-01", {"views": 5})

    def post(self, path, data):
        return self.client.post(path, data={"signed_request": signed({"algorithm": "HMAC-SHA256", **data})})

    def accounts(self):
        return {c["account_id"] for c in db.connections(self.uid, "instagram")}

    def test_unsigned_is_refused(self):
        for path in ("/api/instagram/deauthorize", "/api/instagram/data-deletion"):
            r = self.client.post(path, data={"signed_request": signed({"algorithm": "HMAC-SHA256", "user_id": self.ig},
                                                                      "wrong")})
            self.assertEqual(r.status_code, 400)
        self.assertIn(self.ig, self.accounts())

    def test_deauthorize_drops_only_that_connection(self):
        r = self.post("/api/instagram/deauthorize", {"user_id": self.ig})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.accounts(), {"keep" + self.ig})
        JOBS.pop(self.jid, None)
        posts = json.loads((JOBS_DIR / self.jid / "job.json").read_text())["ig_posts"]
        self.assertEqual(len(posts), 2)  # records stay on a plain removal

    def test_data_deletion_deletes_records_and_numbers(self):
        r = self.post("/api/instagram/data-deletion", {"user_id": int(self.ig)})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertRegex(body["confirmation_code"], r"^[0-9a-f]{16}$")
        self.assertTrue(body["url"].endswith("/data-deletion?code=" + body["confirmation_code"]))
        self.assertEqual(self.accounts(), {"keep" + self.ig})
        JOBS.pop(self.jid, None)
        posts = json.loads((JOBS_DIR / self.jid / "job.json").read_text())["ig_posts"]
        self.assertEqual([p["ig_id"] for p in posts], ["keep" + self.ig])
        self.assertEqual(db.reel_snapshots(self.uid, ["m1" + self.ig])["m1" + self.ig], [])
        page = self.client.get("/data-deletion?code=" + body["confirmation_code"]).get_data(as_text=True)
        self.assertIn("done", page)
        page = self.client.get("/data-deletion?code=0000000000000000").get_data(as_text=True)
        self.assertIn("no deletion request", page)
        self.assertNotIn("{{STATUS}}", self.client.get("/data-deletion").get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
