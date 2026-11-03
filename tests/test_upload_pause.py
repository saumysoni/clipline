"""Pause and Resume on a vlog upload: while it's prepared, and on its way to YouTube (web/vlog_upload.py). Also posting
the finished Shorts while another is being remade (web/posting.py)."""
from tests import _env  # noqa: F401  (first: clean settings)

import json
import re
import tempfile
import unittest
from pathlib import Path

import httplib2
from googleapiclient.http import HttpRequest

from tests import fakes as F
from accounts import db
from web import youtube_quota as quota


class Pause(unittest.TestCase):
    def setUp(self):
        F.install()
        F.reset()
        F.RESUMED.clear()
        F.UPLOAD_GATE.set()
        self.u = F.new_user()
        self.c = F.client(self.u)

    def tearDown(self):
        F.SLOW.transcribe = 0
        F.UPLOAD_GATE.set()

    def start(self):
        up = F.upload(self.c, F.test_video(60))
        return self.c.post("/api/vlog/start", data={"upload": up}).json["id"]

    def status(self, jid):
        return self.c.get(f"/api/status/{jid}").json

    def ready(self):
        jid = self.start()
        F.wait(lambda: self.status(jid)["status"] == "ready", timeout=30, what="ready")
        return jid

    def test_preparing_pauses_between_stages_and_carries_on(self):
        F.SLOW.transcribe = 1.0
        jid = self.start()
        F.wait(lambda: self.status(jid).get("stage") == 1, what="transcribing")
        self.assertEqual(self.c.post(f"/api/vlogs/{jid}/pause").json, {"ok": True, "paused": False})
        F.wait(lambda: self.status(jid)["status"] == "paused", timeout=30, what="paused")
        self.assertEqual(self.status(jid)["stage"], 1)  # transcribing finished, the details didn't start
        before = F.AI.kinds().count("meta")
        F.SLOW.transcribe = 0
        self.assertTrue(self.c.post(f"/api/vlogs/{jid}/resume").json["ok"])
        F.wait(lambda: self.status(jid)["status"] == "ready", timeout=30, what="ready")
        self.assertEqual(F.AI.kinds().count("meta"), before + 1)  # asked once, after the pause
        self.assertFalse(self.status(jid).get("vmeta"))

    def test_stop_while_preparing_is_paused_removes_it(self):
        F.SLOW.transcribe = 1.0
        jid = self.start()
        F.wait(lambda: self.status(jid).get("stage") == 1, what="transcribing")
        self.c.post(f"/api/vlogs/{jid}/pause")
        F.wait(lambda: self.status(jid)["status"] == "paused", timeout=30, what="paused")
        self.assertTrue(self.c.post(f"/api/vlogs/{jid}/stop").json["ok"])
        self.assertEqual(self.c.get(f"/api/status/{jid}").status_code, 404)

    def _pause_upload(self):
        F.connect_youtube(self.u["id"])
        jid = self.ready()
        F.UPLOAD_GATE.clear()
        r = self.c.post(f"/api/vlog/{jid}/upload", json={"title": "My video", "privacy": "public"})
        self.assertTrue(r.json["ok"], r.json)
        F.wait(lambda: (self.status(jid).get("vpost") or {}).get("pct") == 40, what="half-way")
        self.assertTrue(self.c.post(f"/api/vlog/{jid}/upload-pause").json["ok"])
        F.UPLOAD_GATE.set()
        F.wait(lambda: self.status(jid)["vpost"]["state"] == "paused", what="paused")
        return jid

    def used_today(self):
        return sum(n for n, _ in db.youtube_uploads(quota.today()).values())

    def test_youtube_upload_pauses_and_resumes_from_the_same_place_counted_once(self):
        jid = self._pause_upload()
        self.assertNotIn("vresume", self.status(jid))  # the upload's address stays on the server
        used = self.used_today()
        self.assertEqual(self.c.post(f"/api/vlog/{jid}/upload", json={"title": "x"}).status_code, 400)
        self.assertEqual(self.c.post(f"/api/vlog/{jid}/shorts", json={"count": 1}).status_code, 400)
        self.assertEqual(self.c.post(f"/api/vlogs/{jid}/delete-video").status_code, 400)
        self.assertTrue(self.c.post(f"/api/vlog/{jid}/upload-resume").json["ok"])
        F.wait(lambda: self.status(jid)["vpost"]["state"] == "done", what="done")
        self.assertEqual(F.RESUMED[-1]["uri"], "https://upload.example/session")
        self.assertEqual(F.RESUMED[-1]["at"], 1234)
        self.assertEqual(self.used_today(), used)  # not counted twice
        self.assertFalse(self.status(jid).get("vresume"))

    def test_cancel_a_paused_upload_gives_the_count_back(self):
        jid = self._pause_upload()
        used = self.used_today()
        self.assertTrue(self.c.post(f"/api/vlog/{jid}/upload-cancel").json["ok"])
        self.assertFalse(self.status(jid).get("vpost"))
        self.assertEqual(self.used_today(), used - 1)
        self.assertEqual(self.c.post(f"/api/vlog/{jid}/upload-cancel").status_code, 400)

    def test_retention_keeps_a_paused_upload_then_drops_it(self):
        from web import retention
        jid = self._pause_upload()
        job = F.job_json(jid)
        self.assertTrue(retention._busy(job))
        self.assertEqual(retention.keep_original(), 72 * 3600)
        retention.sweep_job(jid, now=job["last_edit_at"] + 3600)
        self.assertEqual(self.status(jid)["vpost"]["state"], "paused")  # kept
        retention.sweep_job(jid, now=job["last_edit_at"] + retention.keep_original() + 60)
        post = self.status(jid)["vpost"]
        self.assertEqual(post["state"], "error")
        self.assertIn("paused for too long", post["error"])

    def test_real_uploader_stops_between_pieces_and_carries_on_from_the_byte(self):
        """Against Google's own client: Pause gives the address and byte; Resume sends from that byte, no new upload."""
        from youtube.vlog_upload import UploadPaused, upload_vlog

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "v.mp4"
            path.write_bytes(b"x" * (40 * 1024 * 1024))
            size = path.stat().st_size
            piece = 16 * 1024 * 1024
            seen = []

            class Http:  # stands in for the network under Google's real HttpRequest
                def request(self, uri, method="GET", body=None, headers=None, **kw):
                    h = {k.lower(): v for k, v in (headers or {}).items()}
                    if method == "POST":
                        seen.append("new")
                        return httplib2.Response({"status": "200", "location": "https://up/1"}), b""
                    start, end = re.match(r"bytes (\d+)-(\d+)/", h["content-range"]).groups()
                    seen.append(int(start))
                    if int(end) + 1 >= size:
                        return httplib2.Response({"status": "200"}), b'{"id": "VID"}'
                    return httplib2.Response({"status": "308", "range": f"0-{end}"}), b""

            class YT:
                def videos(self):
                    return self

                def insert(self, part, body, media_body):
                    return HttpRequest(Http(), lambda resp, content: json.loads(content), "https://up/start", method="POST",
                                       body=json.dumps(body), headers={}, resumable=media_body)

            with self.assertRaises(UploadPaused) as got:
                upload_vlog(YT(), path, "t", "d", [], should_pause=lambda: True)
            uri, at = got.exception.uri, got.exception.at
            self.assertEqual((uri, at), ("https://up/1", piece))
            self.assertEqual(seen, ["new", 0])
            seen.clear()
            vid, _ = upload_vlog(YT(), path, "t", "d", [], resume={"uri": uri, "at": at})
            self.assertEqual(vid, "VID")
            self.assertEqual(seen, [piece, 2 * piece])  # no new upload, and from the byte it stopped at


class PostWhatsReady(unittest.TestCase):
    def setUp(self):
        F.install()
        F.reset()
        self.u = F.new_user()
        self.c = F.client(self.u)
        F.connect_youtube(self.u["id"])

    def test_finished_shorts_go_while_another_is_remade(self):
        jid, _ = F.make_shorts(self.c, count=2)
        from web.store import update_short
        update_short(jid, 2, retrying=True)
        rows = [{"idx": 1, "title": "One", "keep": True}, {"idx": 2, "title": "Two", "keep": False}]
        r = self.c.post(f"/api/schedule/{jid}", json={"shorts": rows, "schedule": "now"})
        self.assertTrue(r.json.get("ok"), r.json)
        F.wait(lambda: not F.job_json(jid).get("upload_status") in ("starting", "connecting", "uploading"), what="sent")
        self.assertEqual([u["idx"] for u in F.job_json(jid)["uploads"]], [1])

    def test_a_ticked_short_being_remade_is_refused(self):
        jid, _ = F.make_shorts(self.c, count=2)
        from web.store import update_short
        update_short(jid, 2, retrying=True)
        rows = [{"idx": 1, "title": "One", "keep": True}, {"idx": 2, "title": "Two", "keep": True}]
        r = self.c.post(f"/api/schedule/{jid}", json={"shorts": rows, "schedule": "now"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("Untick", r.json["error"])


if __name__ == "__main__":
    unittest.main()
