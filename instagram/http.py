"""
Talking to Instagram's API: small JSON GET/POST helpers that turn Instagram's errors into plain English.
"""
import json
import urllib.error
import urllib.parse
import urllib.request

from instagram.config import NET_TIMEOUT


class InstagramError(RuntimeError):
    """Something Instagram refused, in words for the creator. .code is Instagram's error code, if any."""
    def __init__(self, msg, code=None, expired=False):
        super().__init__(msg)
        self.code, self.expired = code, expired


def _plain(err, status):
    msg = (err.get("error_user_msg") or err.get("message") or "").strip()
    code, sub = err.get("code"), err.get("error_subcode")
    if code == 190 or status == 401:
        return InstagramError("Your Instagram connection has expired. Click Connect Instagram, then try again.", code, True)
    if code in (10, 200) or "permission" in msg.lower():
        return InstagramError("Instagram didn't allow this. Connect Instagram again and allow every permission "
                              "(and make sure it's a Business or Creator account).", code)
    if code in (4, 17, 32, 613) or sub == 2207042:
        return InstagramError("Instagram's limit for posting by app is reached for now (100 posts a day). Try again later.", code)
    if code == 9004 or sub == 2207052:
        return InstagramError("Instagram couldn't fetch the video. Try again.", code)
    return InstagramError(f"Instagram said: {msg or 'something went wrong'}" + (f" (code {code})" if code else ""), code)


def call(method, url, params=None, data=None, headers=None, timeout=NET_TIMEOUT):
    """JSON from Instagram. params go in the address; data (dict) is sent as a form, (bytes) as the body."""
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    body = urllib.parse.urlencode(data).encode() if isinstance(data, dict) else data
    req = urllib.request.Request(url, data=body, method=method, headers={"User-Agent": "Clipline", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode("utf-8", "replace")).get("error") or {}
        except ValueError:
            err = {}
        if isinstance(err, str):
            err = {"message": err}
        raise _plain(err, e.code) from e
    except OSError as e:
        raise InstagramError("Couldn't reach Instagram. Check your internet connection and try again.") from e
