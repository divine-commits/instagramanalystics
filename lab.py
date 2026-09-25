#!/usr/bin/env python3
"""Post lab fetcher: pulls Instagram post Insights via the official
Instagram API with Instagram Login (graph.instagram.com).

Phase 1 commands (setup and testing):
  lab setup            save your access token into .env
  lab check            confirm the token works and show your account type
  lab refresh          renew your token for another 60 days
  lab recent [N]       list your N most recent posts (default 10)
  lab test <link>      trial-reel / metric test for one post

Uses only the Python standard library, so there's nothing to install.
"""

import getpass
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENV_FILE = HERE / ".env"
REPORTS_DIR = HERE / "reports"

# Asia/Manila is UTC+8 with no daylight saving, so a fixed offset is exact
# and avoids needing the tzdata package on Windows.
MANILA = timezone(timedelta(hours=8), "Asia/Manila")

API_HOST = "https://graph.instagram.com"

MEDIA_FIELDS = [
    "id", "shortcode", "permalink", "media_type", "media_product_type",
    "timestamp", "caption", "like_count", "comments_count",
]
# Fields we try one by one, because some only exist on some post types
# (or may not exist at all) and one bad field would fail the whole call.
EXTRA_FIELDS = ["is_shared_to_feed", "trial_params", "view_count"]

# Candidate insight metric names. `lab test` asks for each one separately
# and records which ones Instagram accepts for that kind of post.
CANDIDATE_METRICS = [
    "views", "reach", "likes", "comments", "shares", "saved",
    "total_interactions", "follows", "profile_visits", "profile_activity",
    "ig_reels_avg_watch_time", "ig_reels_video_view_total_time",
    "reels_skip_rate", "skip_rate", "reposts", "navigation", "replies",
]


# ---------- .env handling ----------

def load_env():
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def save_env(env):
    lines = ["# Post lab secrets. Never share or commit this file."]
    lines += [f"{k}={v}" for k, v in env.items()]
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        os.chmod(ENV_FILE, 0o600)
    except OSError:
        pass


def mask(token):
    if not token:
        return "(none)"
    return f"{token[:4]}…{token[-4:]} ({len(token)} characters)"


def get_token(env):
    token = env.get("IG_ACCESS_TOKEN")
    if not token:
        die("No access token saved yet. Run:  lab setup")
    return token


# ---------- API calls ----------

class ApiError(Exception):
    pass


_SECRETS = []


def scrub(text):
    for s in _SECRETS:
        if s:
            text = text.replace(s, "***")
    return text


def api_get(path_or_url, params=None, token=None):
    if path_or_url.startswith("http"):
        url = path_or_url  # a paging "next" URL already has everything
    else:
        env = load_env()
        version = env.get("IG_API_VERSION", "").strip()
        prefix = f"/{version}" if version else ""
        q = dict(params or {})
        if token:
            q["access_token"] = token
        url = f"{API_HOST}{prefix}/{path_or_url.lstrip('/')}?{urllib.parse.urlencode(q)}"
    req = urllib.request.Request(url, headers={"User-Agent": "post-lab/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try:
            err = json.loads(body).get("error", {})
            msg = err.get("message", body)
            code = err.get("code")
            msg = f"{msg} (code {code})" if code else msg
        except ValueError:
            msg = body[:300]
        raise ApiError(scrub(msg)) from None
    except urllib.error.URLError as e:
        raise ApiError(scrub(f"Couldn't reach Instagram: {e.reason}")) from None


# ---------- helpers ----------

def die(msg):
    print(f"\n{msg}\n")
    sys.exit(1)


def parse_ig_time(ts):
    # Instagram sends e.g. 2026-09-20T10:00:00+0000
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S%z")


def manila(ts):
    return parse_ig_time(ts).astimezone(MANILA).strftime("%Y-%m-%d %H:%M")


def shortcode_from_link(link):
    m = re.search(r"instagram\.com/(?:[^/?#]+/)?(?:reels?|p|tv)/([A-Za-z0-9_-]+)", link)
    if not m:
        die("That doesn't look like an Instagram post link. It should contain /reel/, /reels/ or /p/.")
    return m.group(1)


def fetch_fields(media_id, token, fields):
    try:
        return api_get(media_id, {"fields": ",".join(fields)}, token)
    except ApiError:
        return {}


def iter_media(token, fields, limit=50):
    data = api_get("me/media", {"fields": ",".join(fields), "limit": limit}, token)
    while True:
        for item in data.get("data", []):
            yield item
        nxt = data.get("paging", {}).get("next")
        if not nxt:
            return
        data = api_get(nxt)


def fmt_type(item):
    mt, pt = item.get("media_type"), item.get("media_product_type")
    if pt == "REELS":
        return "Reel"
    if mt == "CAROUSEL_ALBUM":
        return "Carousel"
    if mt == "IMAGE":
        return "Single photo"
    if mt == "VIDEO":
        return "Video"
    return f"{mt}/{pt}"


# ---------- commands ----------

def cmd_setup(args):
    print("\nPaste your Instagram access token below and press Enter.")
    print("(Nothing will show on screen while you paste. That's normal and keeps it private.)\n")
    token = getpass.getpass("Token: ").strip()
    if len(token) < 50:
        die("That looks too short to be a token. Copy it again from the Meta dashboard and retry.")
    _SECRETS.append(token)
    try:
        me = api_get("me", {"fields": "user_id,username,account_type"}, token)
    except ApiError as e:
        die(f"Instagram rejected that token: {e}")
    env = load_env()
    env["IG_ACCESS_TOKEN"] = token
    env["IG_USER_ID"] = str(me.get("user_id") or me.get("id", ""))
    env["IG_USERNAME"] = me.get("username", "")
    # Dashboard-generated tokens last 60 days. We can't read the exact date
    # back from Instagram, so record an estimate; `lab refresh` replaces it
    # with the real expiry.
    exp = datetime.now(MANILA) + timedelta(days=60)
    env["IG_TOKEN_EXPIRES"] = exp.strftime("%Y-%m-%d %H:%M")
    env["IG_TOKEN_EXPIRES_IS_ESTIMATE"] = "yes"
    save_env(env)
    print(f"\n✅ Saved token {mask(token)} for @{env['IG_USERNAME']}.")
    print(f"   It should expire around {env['IG_TOKEN_EXPIRES']} (Asia/Manila).")
    print("   You can run `lab refresh` any time after it's 24 hours old to get a fresh 60 days.\n")


def cmd_check(args):
    env = load_env()
    token = get_token(env)
    _SECRETS.append(token)
    try:
        me = api_get("me", {"fields": "user_id,username,account_type,media_count"}, token)
    except ApiError as e:
        die(f"❌ The token didn't work: {e}\n   If it expired, generate a new one in the Meta dashboard and run `lab setup`.")
    kind = {"BUSINESS": "Business", "MEDIA_CREATOR": "Creator"}.get(me.get("account_type"), me.get("account_type"))
    print(f"\n✅ Connected as @{me.get('username')}")
    print(f"   Account type: {kind}")
    print(f"   Posts on account: {me.get('media_count')}")
    note = " (estimate)" if env.get("IG_TOKEN_EXPIRES_IS_ESTIMATE") == "yes" else ""
    print(f"   Token {mask(token)} expires {env.get('IG_TOKEN_EXPIRES', 'unknown')} (Asia/Manila){note}\n")


def cmd_refresh(args):
    env = load_env()
    token = get_token(env)
    _SECRETS.append(token)
    try:
        r = api_get("refresh_access_token", {"grant_type": "ig_refresh_token"}, token)
    except ApiError as e:
        die(f"❌ Refresh failed: {e}\n   Tokens can only be refreshed once they're at least 24 hours old and not yet expired.\n"
            "   If yours has expired, generate a new one in the Meta dashboard and run `lab setup`.")
    new = r["access_token"]
    _SECRETS.append(new)
    exp = datetime.now(MANILA) + timedelta(seconds=int(r.get("expires_in", 0)))
    env["IG_ACCESS_TOKEN"] = new
    env["IG_TOKEN_EXPIRES"] = exp.strftime("%Y-%m-%d %H:%M")
    env["IG_TOKEN_EXPIRES_IS_ESTIMATE"] = "no"
    save_env(env)
    print(f"\n✅ Token renewed {mask(new)}. New expiry: {env['IG_TOKEN_EXPIRES']} (Asia/Manila).\n")


def cmd_recent(args):
    n = int(args[0]) if args else 10
    env = load_env()
    token = get_token(env)
    _SECRETS.append(token)
    fields = ["id", "shortcode", "permalink", "media_type", "media_product_type", "timestamp", "is_shared_to_feed"]
    try:
        items = []
        for item in iter_media(token, fields, limit=min(n, 50)):
            items.append(item)
            if len(items) >= n:
                break
    except ApiError:
        # is_shared_to_feed might be rejected; retry without it
        fields.remove("is_shared_to_feed")
        items = []
        for item in iter_media(token, fields, limit=min(n, 50)):
            items.append(item)
            if len(items) >= n:
                break
    print(f"\nYour {len(items)} most recent posts (times in Asia/Manila):\n")
    for i, it in enumerate(items, 1):
        stf = it.get("is_shared_to_feed")
        stf_txt = "" if stf is None else f"  shared_to_feed={stf}"
        print(f"{i:>2}. {manila(it['timestamp'])}  {fmt_type(it):<12} "
              f"media_type={it.get('media_type')}  product_type={it.get('media_product_type')}{stf_txt}")
        print(f"    id={it['id']}  {it.get('permalink')}")
    print()


def probe_metrics(media_id, token):
    """Ask for each candidate metric separately and record the result."""
    results = {}
    for m in CANDIDATE_METRICS:
        try:
            r = api_get(f"{media_id}/insights", {"metric": m}, token)
            entry = (r.get("data") or [{}])[0]
            vals = entry.get("values")
            value = vals[0].get("value") if vals else entry.get("total_value", {}).get("value")
            results[m] = {"ok": True, "value": value}
        except ApiError as e:
            results[m] = {"ok": False, "error": str(e)}
    # A deliberately bogus metric makes Instagram reply with its own list of
    # valid metrics for this post, which is the most up-to-date source.
    valid_list = None
    try:
        api_get(f"{media_id}/insights", {"metric": "post_lab_probe"}, token)
    except ApiError as e:
        m = re.search(r"one of the following values:\s*(.+?)(?:\s*\(code|$)", str(e))
        valid_list = m.group(1).strip() if m else str(e)
    return results, valid_list


def cmd_test(args):
    if not args:
        die("Usage:  lab test <instagram post link>")
    link = args[0]
    code = shortcode_from_link(link)
    env = load_env()
    token = get_token(env)
    _SECRETS.append(token)

    print(f"\nLooking for post {code} in your media list…")
    found, scanned = None, 0
    try:
        for item in iter_media(token, ["id", "shortcode", "permalink", "timestamp"]):
            scanned += 1
            if item.get("shortcode") == code or f"/{code}/" in (item.get("permalink") or ""):
                found = item
                break
    except ApiError as e:
        die(f"❌ Couldn't read your media list: {e}")

    report = {"link": link, "shortcode": code, "checked_at": datetime.now(MANILA).isoformat(),
              "posts_scanned": scanned, "in_media_list": bool(found)}

    if not found:
        print(f"❌ Not found. I checked all {scanned} posts Instagram returned and this one isn't among them.")
        print("   So Instagram's API does NOT list this post.\n")
        save_report(code, report)
        return

    media_id = found["id"]
    print(f"✅ Found it (after checking {scanned} posts). Media ID {media_id}\n")

    details = fetch_fields(media_id, token, MEDIA_FIELDS)
    extras = {}
    for f in EXTRA_FIELDS:
        r = fetch_fields(media_id, token, ["id", f])
        extras[f] = r.get(f, "(not available)")
    report["details"] = details
    report["extra_fields"] = extras

    print(f"Posted:             {manila(details['timestamp'])} (Asia/Manila)")
    print(f"Type:               {fmt_type(details)}  (media_type={details.get('media_type')}, product_type={details.get('media_product_type')})")
    for f, v in extras.items():
        print(f"{f + ':':<20}{v}")

    print("\nTrying each Insights metric one by one…")
    results, valid_list = probe_metrics(media_id, token)
    report["metrics"] = results
    report["instagram_valid_metric_list"] = valid_list
    for m, r in results.items():
        if r["ok"]:
            print(f"  ✅ {m:<32} {r['value']}")
        else:
            print(f"  —  {m:<32} not available")
    if valid_list:
        print(f"\nInstagram says these metrics are valid for this post:\n  {valid_list}")

    path = save_report(code, report)
    print(f"\nFull results saved to {path.relative_to(HERE)}")
    print("Please copy everything above (from 'Looking for post') and paste it back to me.\n")


def save_report(code, report):
    REPORTS_DIR.mkdir(exist_ok=True)
    path = REPORTS_DIR / f"test-{code}-{datetime.now(MANILA).strftime('%Y%m%d-%H%M')}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


COMMANDS = {
    "setup": cmd_setup, "check": cmd_check, "refresh": cmd_refresh,
    "recent": cmd_recent, "test": cmd_test,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        sys.exit(0 if len(sys.argv) < 2 else 1)
    try:
        COMMANDS[sys.argv[1]](sys.argv[2:])
    except ApiError as e:
        die(f"❌ Instagram API error: {e}")


if __name__ == "__main__":
    main()
