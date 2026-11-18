"""
Getting a vlog's video from a link the creator pasted: Google Drive, Dropbox, OneDrive / SharePoint, or a direct https
link to the file. Clippers usually get the vlogger's original this way (a shared folder), and it's sharper than any
YouTube copy.

Never YouTube: Pit Crew doesn't download videos from YouTube (CLAUDE.md gotcha 10). youtube/links.py refuses those
links before a job starts.

The server fetches an address a person typed, so (apart from Drive, which gdown fetches from Google's own hosts) every
request goes through _SafeHTTPS: https only, and the address the name resolves to must be a public one (never this
server, the local network or the cloud's metadata service at 169.254.169.254), checked on every redirect and on the
very address connected to (so a name can't resolve to a public address for the check and a private one for the
connection).

No web code here (the cloud worker will call it): the caller passes the size limits and check(), which raises to stop.
"""
import base64
import http.client
import ipaddress
import socket
import ssl
import urllib.parse
from pathlib import Path

CHUNK = 1 << 20  # 1 MB
TIMEOUT = 30  # seconds to connect, and between two pieces of the file
MAX_REDIRECTS = 5

SHARING = ("Couldn't get the video from that link. Make sure it's shared with \"Anyone with the link\" (no sign-in "
           "needed), or upload the file instead.")
NOT_VIDEO = ("That link opens a web page, not a video file. Share the video itself with \"Anyone with the link\" and "
             "paste that link, or upload the file instead.")


# YouTube's pages and the servers its videos stream from: never fetched (gotcha 10), so a direct link to them is refused
YOUTUBE_HOSTS = ("youtube.com", "youtube-nocookie.com", "googlevideo.com", "ytimg.com", "youtube.googleapis.com")


def provider(url):
    """Who hosts a pasted link: "youtube" (refused), "drive", "dropbox", "onedrive", "sharepoint", "web" (any other
    https site), or "" when it isn't an https / http web address. Used by youtube/links.py link_kind() and below."""
    url = (url or "").strip()
    if not url:
        return ""
    p = urllib.parse.urlparse(url if "://" in url else "https://" + url)
    host = (p.hostname or "").lower()
    if p.scheme not in ("http", "https") or "." not in host:
        return ""
    if host == "youtu.be" or host.endswith(YOUTUBE_HOSTS):
        return "youtube"
    if host in ("drive.google.com", "docs.google.com"):
        return "drive"
    if host in ("dropbox.com", "www.dropbox.com"):
        return "dropbox"
    if host in ("1drv.ms", "onedrive.live.com"):
        return "onedrive"
    if host.endswith(".sharepoint.com"):
        return "sharepoint"
    return "web"


def download_address(url):
    """The address that answers with the file itself, for a sharing link of `url`'s provider."""
    url = url.strip()
    if "://" not in url:
        url = "https://" + url
    kind = provider(url)
    p = urllib.parse.urlparse(url)
    if kind in ("dropbox", "sharepoint"):
        q = [(k, v) for k, v in urllib.parse.parse_qsl(p.query, keep_blank_values=True) if k not in ("dl", "download", "raw")]
        q.append(("dl", "1") if kind == "dropbox" else ("download", "1"))
        return urllib.parse.urlunparse(p._replace(scheme="https", query=urllib.parse.urlencode(q)))
    if kind == "onedrive":  # OneDrive's sharing API: "u!" + the link in unpadded base64url
        token = base64.urlsafe_b64encode(url.encode("utf-8")).decode("ascii").rstrip("=")
        return f"https://api.onedrive.com/v1.0/shares/u!{token}/root/content"
    return urllib.parse.urlunparse(p._replace(scheme="https"))


# ---------------------------------------------------------------- safe fetching --------------------------------------

def public_address(ip):
    """True for an address on the public internet (not this server, a private network, link-local, multicast...)."""
    try:
        ip = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def _resolve(host, port):
    """The public addresses `host` resolves to, or RuntimeError (none, or any that isn't public)."""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as e:
        raise RuntimeError("Couldn't find the site in that link. Check the link, or upload the file instead.") from e
    addrs = [info[4][0] for info in infos]
    if not addrs or not all(public_address(a) for a in addrs):
        print(f"Refused a video link to {host}: it resolves to {addrs} (not public).")
        raise RuntimeError("Pit Crew can't fetch videos from that address. Use a Google Drive, Dropbox or OneDrive "
                           "link, or upload the file instead.")
    return addrs


class _SafeHTTPS(http.client.HTTPSConnection):
    """https to a public address only: the name is resolved and checked here, and the socket opened to that exact
    address (the certificate is still checked against the name)."""

    def connect(self):
        last = None
        for addr in _resolve(self.host, self.port):
            try:
                sock = socket.create_connection((addr, self.port), self.timeout)
                break
            except OSError as e:
                last = e
        else:
            raise RuntimeError("Couldn't reach the site in that link. Try again in a minute, or upload the file "
                               "instead.") from last
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def _open(url):
    """(connection, response) for url after following redirects; the response's status is 2xx."""
    ctx = ssl.create_default_context()
    for _ in range(MAX_REDIRECTS + 1):
        p = urllib.parse.urlparse(url)
        if p.scheme != "https" or not p.hostname:
            raise RuntimeError("Pit Crew only fetches videos from https links. Upload the file instead.")
        conn = _SafeHTTPS(p.hostname, p.port or 443, timeout=TIMEOUT, context=ctx)
        target = (p.path or "/") + (f"?{p.query}" if p.query else "")
        try:
            conn.request("GET", target, headers={"User-Agent": "PitCrew/1.0", "Accept": "*/*"})
            r = conn.getresponse()
        except RuntimeError:
            conn.close()
            raise
        except (OSError, http.client.HTTPException) as e:
            conn.close()
            raise RuntimeError("Couldn't reach the site in that link. Try again in a minute, or upload the file "
                               "instead.") from e
        if r.status in (301, 302, 303, 307, 308) and r.getheader("Location"):
            url = urllib.parse.urljoin(url, r.getheader("Location"))
            r.close()
            conn.close()
            continue
        if 200 <= r.status < 300:
            return conn, r
        r.close()
        conn.close()
        if r.status in (401, 403, 404, 410):
            raise RuntimeError(SHARING)
        raise RuntimeError(f"The site in that link didn't hand over the video (it answered {r.status}). Try again in a "
                           "minute, or upload the file instead.")
    raise RuntimeError("That link sends Pit Crew from page to page without reaching the video. Paste the video's own "
                       "sharing link, or upload the file instead.")


# ---------------------------------------------------------------- the download ---------------------------------------

def too_big(size, max_bytes):
    return (f"That video is {size / 1e9:.1f} GB; Pit Crew takes videos up to {max_bytes / 1e9:.0f} GB. Export a "
            "smaller file (1080p is plenty for Shorts).")


NO_ROOM = "Pit Crew doesn't have room for this video right now. Try again later; if it keeps happening, tell us."


def _limit(size, max_bytes, room):
    if max_bytes and size > max_bytes:
        raise RuntimeError(too_big(size, max_bytes))
    if room is not None and size > room:
        print(f"No room for a {size / 1e9:.1f} GB linked video ({room / 1e9:.1f} GB to spare).")
        raise RuntimeError(NO_ROOM)


def download_video(url, dest, max_bytes=None, room=None, check=None):
    """Save the video behind a sharing link at `dest`. max_bytes: the largest video Pit Crew takes; room: bytes this
    server can spare now; check(): called between pieces, raises to stop (Pause / Stop). RuntimeError (a plain
    sentence) when it can't."""
    dest = Path(dest)
    # Not "source.mp4.part": the pages find a vlog's video with glob("source.*"), and a half download must never count
    part = dest.with_name(".download.part")
    kind = provider(url)
    if not kind:
        raise RuntimeError("That doesn't look like a link. Paste the video's sharing link, or upload the file instead.")
    if kind == "youtube":
        raise RuntimeError("Pit Crew can't download videos from YouTube (YouTube's rules don't allow it). Upload the "
                           "original video file or use a Google Drive, Dropbox or OneDrive link instead.")
    try:
        if kind == "drive":
            _drive(url, part)
            size = part.stat().st_size if part.exists() else 0
            if size < 1000:
                raise RuntimeError(SHARING)
            _limit(size, max_bytes, room)
        else:
            _fetch(download_address(url), part, max_bytes, room, check)
        part.replace(dest)
    finally:
        if part.exists():
            part.unlink()
    return dest


def _drive(url, part):
    import gdown
    try:
        gdown.download(url=url, output=str(part), quiet=True, fuzzy=True)
    except Exception as e:  # noqa: BLE001  (gdown raises its own kinds for private or missing files)
        print(f"Google Drive download failed: {e!r}")
        raise RuntimeError(SHARING) from e


def _fetch(url, part, max_bytes, room, check):
    conn, r = _open(url)
    try:
        ctype = (r.getheader("Content-Type") or "").split(";")[0].strip().lower()
        if ctype in ("text/html", "application/xhtml+xml"):  # a sign-in or "request access" page, not the file
            raise RuntimeError(NOT_VIDEO)
        try:
            size = int(r.getheader("Content-Length") or 0)
        except ValueError:
            size = 0
        if size:
            _limit(size, max_bytes, room)
        got = 0
        with open(part, "wb") as f:
            while True:
                if check:
                    check()
                try:
                    piece = r.read(CHUNK)
                except (OSError, http.client.HTTPException) as e:
                    raise RuntimeError("The connection to the site in that link dropped. Try again, or upload the "
                                       "file instead.") from e
                if not piece:
                    break
                got += len(piece)
                _limit(got, max_bytes, room)  # no Content-Length (or a wrong one): still never past the limits
                f.write(piece)
        if got < 1000:
            raise RuntimeError(SHARING)
    finally:
        r.close()
        conn.close()
