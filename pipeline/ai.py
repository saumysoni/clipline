"""
Talking to the AI (Gemini by default, OpenAI with AI_PROVIDER=openai).

Every AI feature calls ai_json(). It retries busy models, skips retired ones and parses the JSON.
Pass images as image_part(bytes).
"""
import json
import os
import re
import time


# Current Flash models, newest first (checked October 2026).
FALLBACK_MODELS = ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.5-flash", "gemini-2.5-flash"]


OPENAI_FALLBACK_MODELS = ["gpt-5.4-mini", "gpt-5-mini", "gpt-4.1-mini"]


BUSY_WAITS = [15, 45]  # seconds to wait before another round when every model is busy


TIMEOUT = 180  # seconds one request may take; without a limit, a request that never answers hangs forever


def gemini_error_kind(e):
    """Sort a Gemini error into: busy, limit, missing, bad_key or other."""
    code = getattr(e, "code", None)
    msg = str(e).lower()
    if code in (500, 502, 503, 504) or any(k in msg for k in ("unavailable", "overloaded", "high demand",
                                                               "deadline", "internal error", "timed out", "timeout")) \
            or "Timeout" in type(e).__name__:
        return "busy"
    if code == 429 or "resource_exhausted" in msg or "quota" in msg:
        return "limit"
    if code == 404 or "not found" in msg or "not_found" in msg or "is not supported" in msg:
        return "missing"
    if code in (401, 403) or "api key" in msg or "api_key" in msg or "permission" in msg:
        return "bad_key"
    return "other"


def openai_error_kind(e):
    """Sort an OpenAI error into: busy, limit, no_credit, missing, bad_key or other."""
    code = getattr(e, "status_code", None)
    msg = str(e).lower()
    name = type(e).__name__
    if (code is not None and code >= 500) or name in ("APIConnectionError", "APITimeoutError"):
        return "busy"
    if "insufficient_quota" in msg:
        return "no_credit"  # out of prepaid credit, waiting won't help
    if code == 429:
        return "limit"
    if code == 404 or "model_not_found" in msg or "does not exist" in msg:
        return "missing"
    if code in (401, 403):
        return "bad_key"
    return "other"


def image_part(data, mime_type="image/jpeg"):
    """An image for ai_json(), in a form every provider understands."""
    return {"image": data, "mime_type": mime_type}


def ai_provider():
    return (os.getenv("AI_PROVIDER") or "gemini").strip().lower()


def has_key(provider):
    """True if .env has the API key that `provider` (gemini or openai) needs."""
    return bool(os.getenv({"gemini": "GEMINI_API_KEY", "openai": "OPENAI_API_KEY"}.get(provider, "")))


def ai_json(contents, progress=lambda pct, msg: None, temperature=0.4, busy_hint="", provider=None,
            timeout=TIMEOUT, busy_waits=None):
    """Ask the AI for JSON: `provider` if given ("gemini" or "openai"), else AI_PROVIDER in .env.

    `contents` is a string, or a list of strings and image_part()s. Returns the parsed JSON.
    timeout: seconds per request (a timed-out request counts as busy). busy_waits: the waits between
    rounds when every model is busy (default BUSY_WAITS; [] = one round, for callers in a hurry).
    """
    provider = (provider or ai_provider()).strip().lower()
    if provider == "openai":
        return openai_json(contents, progress, temperature, busy_hint, timeout, busy_waits)
    if provider != "gemini":
        raise RuntimeError(f"AI_PROVIDER in .env is '{provider}', which Clipline doesn't know. "
                           "Set it to gemini or openai and restart.")
    return gemini_json(contents, progress, temperature, busy_hint, timeout, busy_waits)


def ask_models(name, candidates, call, error_kind, fatal, progress, busy_hint, busy_msg, limit_msg, none_msg,
               busy_waits=None):
    """Run call(model) on each model in turn and return the first answer.

    Busy models are retried in rounds (waits in BUSY_WAITS), missing or limited models are skipped,
    and errors listed in `fatal` stop at once with that message.
    """
    resp, problems = None, []
    # Each round tries every model once; if they were all busy, wait a bit and go again.
    for wait in [0] + list(BUSY_WAITS if busy_waits is None else busy_waits):
        if wait:
            progress(10, f"{name} is busy, trying again in {wait} seconds")
            time.sleep(wait)
        retry_later = []
        for model in candidates:
            try:
                resp = call(model)
                break
            except Exception as e:  # noqa: BLE001
                kind = error_kind(e)
                if kind in fatal:
                    raise RuntimeError(fatal[kind]) from e
                if kind == "other":
                    raise
                problems.append(kind)
                print(f"{name} model '{model}': {kind}.")
                if kind == "busy":
                    retry_later.append(model)  # missing models and used-up limits aren't retried
                if model != candidates[-1]:
                    progress(10, f"Trying another {name} model")
        if resp is not None or not retry_later:
            break
        candidates = retry_later
    if resp is None:
        if "busy" in problems:
            raise RuntimeError(busy_msg + busy_hint)
        if "limit" in problems:
            raise RuntimeError(limit_msg + busy_hint)
        raise RuntimeError(none_msg)
    return resp


def parse_ai_json(text, name):
    text = re.sub(r"^```(?:json)?|```$", "", (text or "").strip(), flags=re.M).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"[\[{].*[\]}]", text, flags=re.S)  # salvage JSON wrapped in extra words
        if not m:
            raise RuntimeError(f"{name}'s answer wasn't in the expected format. Please try again.")
        return json.loads(m.group(0))


def candidate_models(env_name, fallbacks):
    wanted = os.getenv(env_name) or fallbacks[0]
    return [wanted] + [m for m in fallbacks if m != wanted]


def gemini_json(contents, progress=lambda pct, msg: None, temperature=0.4, busy_hint="", timeout=TIMEOUT,
                busy_waits=None):
    """Ask Gemini for JSON, trying the model from .env first and then the other current models.

    Gemini sometimes answers "busy" (503) or "limit reached" (429): busy models are retried in rounds
    (waits in BUSY_WAITS), missing or limited models are skipped. `contents` may be a string or a list
    of strings and image_part()s. Returns the parsed JSON (dict or list).
    """
    from google import genai
    from google.genai import types

    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is missing. Add it to the .env file (see README).")
    client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=int(timeout * 1000)))
    if isinstance(contents, list):
        contents = [types.Part.from_bytes(data=c["image"], mime_type=c["mime_type"]) if isinstance(c, dict)
                    else c for c in contents]
    config = {"response_mime_type": "application/json", "temperature": temperature,
              "automatic_function_calling": {"disable": True}}
    resp = ask_models(
        "Gemini", candidate_models("GEMINI_MODEL", FALLBACK_MODELS),
        lambda model: client.models.generate_content(model=model, contents=contents, config=config),
        gemini_error_kind,
        {"bad_key": "Gemini refused the API key. Check GEMINI_API_KEY in the .env file "
                    "(create a fresh key at https://aistudio.google.com/apikey)."},
        progress, busy_hint,
        busy_msg="Gemini is overloaded right now (this is on Google's side). ",
        limit_msg="Gemini's free usage limit is used up for now. Try again in a while (or tomorrow). ",
        none_msg="None of the Gemini models are available to this API key. "
                 "Put a current Flash model name in GEMINI_MODEL in .env.", busy_waits=busy_waits)
    return parse_ai_json(resp.text, "Gemini")


def openai_json(contents, progress=lambda pct, msg: None, temperature=0.4, busy_hint="", timeout=TIMEOUT,
                busy_waits=None):
    """Ask OpenAI for JSON, trying OPENAI_MODEL first and then the other current models (same retry
    rules as gemini_json()). OpenAI's JSON mode only returns objects, so a requested list comes back
    wrapped in an object; callers already accept that.
    """
    import base64

    from openai import OpenAI

    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY is missing. Add it to the .env file (see README), "
                           "or set AI_PROVIDER=gemini.")
    client = OpenAI(api_key=key, max_retries=0, timeout=timeout)
    parts = []
    for c in contents if isinstance(contents, list) else [contents]:
        if isinstance(c, dict):
            url = f"data:{c['mime_type']};base64," + base64.b64encode(c["image"]).decode()
            parts.append({"type": "image_url", "image_url": {"url": url}})
        else:
            parts.append({"type": "text", "text": c})
    messages = [
        {"role": "system", "content": "Reply with one JSON object and nothing else. If you are asked for "
                                      "a list, put it in the object as {\"items\": [...]}."},
        {"role": "user", "content": parts},
    ]
    no_temperature = set()  # reasoning models only accept their default temperature

    def call(model):
        args = {"model": model, "messages": messages, "response_format": {"type": "json_object"}}
        if model not in no_temperature:
            args["temperature"] = temperature
        try:
            return client.chat.completions.create(**args)
        except Exception as e:  # noqa: BLE001
            if "temperature" in str(e).lower() and "temperature" in args:
                no_temperature.add(model)
                args.pop("temperature")
                return client.chat.completions.create(**args)
            raise

    resp = ask_models(
        "OpenAI", candidate_models("OPENAI_MODEL", OPENAI_FALLBACK_MODELS), call, openai_error_kind,
        {"bad_key": "OpenAI refused the API key. Check OPENAI_API_KEY in the .env file "
                    "(create a key at https://platform.openai.com/api-keys).",
         "no_credit": "Your OpenAI account has no credit left. Add credit at "
                      "https://platform.openai.com/settings/organization/billing and try again."},
        progress, busy_hint,
        busy_msg="OpenAI is overloaded right now (this is on OpenAI's side). ",
        limit_msg="OpenAI's rate limit was reached. Wait a minute and try again. ",
        none_msg="None of the OpenAI models are available to this API key. "
                 "Put a current model name in OPENAI_MODEL in .env.", busy_waits=busy_waits)
    return parse_ai_json(resp.choices[0].message.content, "OpenAI")
