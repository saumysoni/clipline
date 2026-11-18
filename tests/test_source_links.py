"""The video from a link: Google Drive, Dropbox, OneDrive / SharePoint or a direct https link (pipeline/source_link.py,
youtube/links.py, the start routes). No internet: the network is faked below, and the safety checks (public addresses
only, https only, on every redirect) are tested without connecting anywhere."""
from tests import fakes as F

import base64
import io
import shutil
import socket
import tempfile
import unittest
import urllib.parse
from pathlib import Path
from unittest import mock

from pipeline import source_link as SL
from youtube.links import link_kind, video_link_problem, youtube_link_problem


class Kinds(unittest.TestCase):
    def test_every_kind(self):
        cases = {
            "https://drive.google.com/file/d/abc/view": "drive_file",
            "https://www.dropbox.com/scl/fi/abc/trip.mp4?rlkey=k&dl=0": "dropbox",
            "https://www.dropbox.com/s/abc/trip.mp4?dl=0": "dropbox",
            "https://www.dropbox.com/scl/fo/abc/xyz?rlkey=k": "dropbox_folder",
            "https://1drv.ms/v/s!AbCdEf": "onedrive",
            "https://onedrive.live.com/?cid=1&resid=2": "onedrive",
            "https://team.sharepoint.com/:v:/g/abc": "onedrive",
            "https://cdn.example.com/raw/trip.mp4": "direct",
            "https://youtu.be/dQw4w9WgXcQ": "youtube",
            "https://rr3---sn-abc.googlevideo.com/videoplayback?id=1": "youtube_page",
            "hello there": "other",
            "": "",
        }
        for url, kind in cases.items():
            self.assertEqual(link_kind(url), kind, url)

    def test_problems(self):
        for ok in ("https://www.dropbox.com/scl/fi/abc/t.mp4?dl=0", "https://1drv.ms/v/s!x", "https://a.example/v.mp4"):
            self.assertIsNone(video_link_problem(ok), ok)
        self.assertIn("can't download videos from YouTube", video_link_problem("https://youtu.be/dQw4w9WgXcQ"))
        self.assertIn("Dropbox folder", video_link_problem("https://www.dropbox.com/scl/fo/abc/x"))
        self.assertIn("Dropbox link", youtube_link_problem("https://www.dropbox.com/scl/fi/abc/t.mp4"))
        self.assertIn("YouTube video link", youtube_link_problem("https://a.example/v.mp4"))
        self.assertIsNone(youtube_link_problem("https://youtu.be/dQw4w9WgXcQ"))

    def test_download_addresses(self):
        d = urllib.parse.urlparse(SL.download_address("https://www.dropbox.com/scl/fi/abc/t.mp4?rlkey=k&dl=0"))
        self.assertEqual(urllib.parse.parse_qs(d.query), {"rlkey": ["k"], "dl": ["1"]})
        sp = SL.download_address("https://team.sharepoint.com/:v:/g/abc?e=1")
        self.assertIn("download=1", sp)
        od = SL.download_address("https://1drv.ms/v/s!AbCdEf")
        token = od.split("/shares/u!")[1].split("/")[0]
        self.assertEqual(base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)).decode(), "https://1drv.ms/v/s!AbCdEf")
        self.assertTrue(SL.download_address("http://a.example/v.mp4").startswith("https://"))

    def test_youtube_video_servers_never_fetched(self):
        with mock.patch.object(SL, "_open", side_effect=AssertionError("fetched")), self.assertRaises(RuntimeError) as e:
            SL.download_video("https://rr1---sn-x.googlevideo.com/videoplayback?id=1", Path(tempfile.mkdtemp()) / "v.mp4")
        self.assertIn("YouTube", str(e.exception))


class Safety(unittest.TestCase):
    def test_public_addresses_only(self):
        for bad in ("127.0.0.1", "10.0.0.5", "192.168.1.2", "172.16.0.1", "169.254.169.254", "::1", "fd00::1",
                    "::ffff:127.0.0.1", "0.0.0.0", "100.64.0.1", "not an ip"):
            self.assertFalse(SL.public_address(bad), bad)
        for good in ("8.8.8.8", "142.250.72.14", "2606:4700:4700::1111"):
            self.assertTrue(SL.public_address(good), good)

    def _resolves_to(self, *addrs):
        return mock.patch.object(socket, "getaddrinfo",
                                 lambda host, port, **kw: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (a, port))
                                                           for a in addrs])

    def test_a_name_pointing_inside_is_refused_before_connecting(self):
        with self._resolves_to("169.254.169.254"), \
                mock.patch.object(socket, "create_connection", side_effect=AssertionError("connected")):
            with self.assertRaises(RuntimeError) as e:
                SL._open("https://metadata.example/latest/")
        self.assertIn("can't fetch videos from that address", str(e.exception))
        with self._resolves_to("8.8.8.8", "10.0.0.1"):  # one private answer is enough to refuse
            with self.assertRaises(RuntimeError):
                SL._resolve("mixed.example", 443)

    def test_https_only(self):
        with self.assertRaises(RuntimeError) as e:
            SL._open("http://a.example/v.mp4")
        self.assertIn("https", str(e.exception))

    def test_every_redirect_goes_through_the_check(self):
        hosts = []

        class Conn:
            def __init__(self, host, port, timeout=None, context=None):
                hosts.append(host)
                self.host = host

            def request(self, *a, **k):
                pass

            def getresponse(self):
                if self.host == "first.example":
                    return FakeResponse(b"", status=302, headers={"Location": "https://second.example/v.mp4"})
                if self.host == "second.example":
                    return FakeResponse(b"", status=301, headers={"Location": "http://third.example/v.mp4"})
                raise AssertionError("not reached")

            def close(self):
                pass

        with mock.patch.object(SL, "_SafeHTTPS", Conn):
            with self.assertRaises(RuntimeError) as e:
                SL._open("https://first.example/v.mp4")
        self.assertEqual(hosts, ["first.example", "second.example"])  # the http hop was refused, not fetched
        self.assertIn("https", str(e.exception))


class FakeResponse:
    def __init__(self, body, status=200, headers=None):
        self.status, self.body, self.headers = status, io.BytesIO(body), headers or {}

    def getheader(self, name, default=None):
        return next((v for k, v in self.headers.items() if k.lower() == name.lower()), default)

    def read(self, n=-1):
        return self.body.read(n)

    def close(self):
        pass


class Download(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.dest = self.dir / "source.mp4"
        self.seen = []

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def serve(self, body, headers=None, status=200):
        def fake_open(url):
            self.seen.append(url)
            return mock.Mock(close=lambda: None), FakeResponse(body, status, headers)
        return mock.patch.object(SL, "_open", fake_open)

    def test_dropbox_file_arrives_whole(self):
        data = F.test_video(5).read_bytes()
        with self.serve(data, {"Content-Type": "video/mp4", "Content-Length": str(len(data))}):
            SL.download_video("https://www.dropbox.com/scl/fi/a/t.mp4?rlkey=k&dl=0", self.dest, max_bytes=1e9, room=1e9)
        self.assertEqual(self.dest.read_bytes(), data)
        self.assertIn("dl=1", self.seen[0])
        self.assertEqual(sorted(f.name for f in self.dir.iterdir()), ["source.mp4"])  # no partial file left

    def test_too_big_by_its_size_or_while_streaming(self):
        body = b"x" * 5000
        with self.serve(body, {"Content-Length": "5000"}), self.assertRaises(RuntimeError) as e:
            SL.download_video("https://a.example/v.mp4", self.dest, max_bytes=4000)
        self.assertIn("GB", str(e.exception))
        with mock.patch.object(SL, "CHUNK", 1000), self.serve(body), self.assertRaises(RuntimeError):  # no length given
            SL.download_video("https://a.example/v.mp4", self.dest, max_bytes=4000)
        with self.serve(body, {"Content-Length": "5000"}), self.assertRaises(RuntimeError) as e:
            SL.download_video("https://a.example/v.mp4", self.dest, max_bytes=1e9, room=100)
        self.assertEqual(str(e.exception), SL.NO_ROOM)
        self.assertEqual(list(self.dir.iterdir()), [])  # nothing half-written left behind

    def test_a_sign_in_page_is_not_a_video(self):
        with self.serve(b"<html>sign in</html>" * 100, {"Content-Type": "text/html; charset=utf-8"}), \
                self.assertRaises(RuntimeError) as e:
            SL.download_video("https://team.sharepoint.com/:v:/g/abc", self.dest)
        self.assertEqual(str(e.exception), SL.NOT_VIDEO)

    def test_stop_mid_download_leaves_at_once(self):
        calls = []

        def check():
            calls.append(1)
            if len(calls) == 3:
                raise InterruptedError("paused")

        with mock.patch.object(SL, "CHUNK", 1000), self.serve(b"x" * 10_000), self.assertRaises(InterruptedError):
            SL.download_video("https://a.example/v.mp4", self.dest, check=check)
        self.assertEqual(len(calls), 3)
        self.assertEqual(list(self.dir.iterdir()), [])

    def test_private_link_says_how_to_share(self):
        def refused(url):
            raise RuntimeError(SL.SHARING)
        with mock.patch.object(SL, "_open", refused), self.assertRaises(RuntimeError) as e:
            SL.download_video("https://1drv.ms/v/s!x", self.dest)
        self.assertIn("Anyone with the link", str(e.exception))

    def test_drive_still_uses_gdown_and_its_limits(self):
        def gdown_saves(url, output, **kw):
            Path(output).write_bytes(b"v" * 5000)
        with mock.patch("gdown.download", gdown_saves):
            SL.download_video("https://drive.google.com/file/d/abc/view", self.dest, max_bytes=1e9)
            self.assertEqual(self.dest.stat().st_size, 5000)
            self.dest.unlink()
            with self.assertRaises(RuntimeError):
                SL.download_video("https://drive.google.com/file/d/abc/view", self.dest, max_bytes=4000)
        self.assertFalse(self.dest.exists())


class Routes(unittest.TestCase):
    def setUp(self):
        F.install()
        F.reset()
        self.c = F.client(F.new_user())

    def test_a_dropbox_link_makes_shorts(self):
        video = F.test_video(60)

        def fake_download(url, dest, **kw):
            self.assertIn("max_bytes", kw)
            self.assertIn("room", kw)
            shutil.copy(video, dest)
            return dest

        with mock.patch("pipeline.download_video", fake_download):
            r = self.c.post("/api/start", data={"link": "https://www.dropbox.com/scl/fi/a/t.mp4?rlkey=k&dl=0",
                                                "count": "1"})
            self.assertEqual(r.status_code, 200, r.json)
            st = F.wait_ready(self.c, r.json["id"])
        self.assertEqual(st["status"], "ready", st.get("error"))
        self.assertEqual(len(st["shorts"]), 1)

    def test_a_failed_link_is_one_plain_sentence(self):
        def private(url, dest, **kw):
            raise RuntimeError(SL.SHARING)
        with mock.patch("pipeline.download_video", private):
            jid = self.c.post("/api/vlog/start", data={"link": "https://1drv.ms/v/s!x"}).json["id"]
            st = F.wait_ready(self.c, jid)
        self.assertEqual(st["status"], "error")
        self.assertIn("Anyone with the link", st["error"])

    def test_youtube_and_folders_refused_up_front(self):
        for url in ("https://youtu.be/dQw4w9WgXcQ", "https://www.dropbox.com/scl/fo/abc/x"):
            for route in ("/api/start", "/api/vlog/start"):
                r = self.c.post(route, data={"link": url})
                self.assertEqual(r.status_code, 400, (route, url))
                self.assertEqual(r.json["field"], "link")


if __name__ == "__main__":
    unittest.main()
