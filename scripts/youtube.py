"""Upload reels from schedule.json to YouTube as Shorts. Runs from GitHub Actions only (no Claude).

Each reel item gets "yt": "queued" | "posted" | "skip", plus yt_id / yt_url / yt_error / yt_at once handled.
Settings live in youtube.json: {"enabled": bool, "privacy": "public"|"private"|"unlisted", "backlog_gap_hours": 5}.

Needs secrets YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN (OAuth "Desktop app" client, youtube.upload scope).
"""
import json, os, sys, time, datetime, urllib.request, urllib.parse, urllib.error

TOKEN_URL = "https://oauth2.googleapis.com/token"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"
API = "https://www.googleapis.com/youtube/v3"
ON_TIME = datetime.timedelta(hours=3)
_token = {"value": None, "exp": 0}


def settings():
    try:
        return json.load(open("youtube.json", encoding="utf-8"))
    except FileNotFoundError:
        return {"enabled": False}


def configured():
    return all(os.environ.get(k) for k in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN"))


def http(req, timeout=120):
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            return r, (json.loads(body) if body else {})
    except urllib.error.HTTPError as e:
        raise RuntimeError("HTTP %s: %s" % (e.code, e.read().decode()[:500]))


def access_token():
    if _token["value"] and time.time() < _token["exp"] - 60:
        return _token["value"]
    data = urllib.parse.urlencode(dict(
        client_id=os.environ["YT_CLIENT_ID"], client_secret=os.environ["YT_CLIENT_SECRET"],
        refresh_token=os.environ["YT_REFRESH_TOKEN"], grant_type="refresh_token")).encode()
    _, d = http(urllib.request.Request(TOKEN_URL, data=data, method="POST"))
    _token["value"], _token["exp"] = d["access_token"], time.time() + int(d.get("expires_in", 3600))
    return _token["value"]


def api(method, path, body=None, **params):
    url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": "Bearer " + access_token(), "Content-Type": "application/json"})
    return http(req)[1]


def title_and_description(caption_path):
    text = open(caption_path, encoding="utf-8").read().strip()
    lines = [l for l in text.split("\n")]
    first = next((l.strip() for l in lines if l.strip() and not l.strip().startswith("#")), "Trading psychology")
    title = first
    if len(title) > 90:
        title = title[:87].rsplit(" ", 1)[0] + "..."
    title = (title + " #Shorts").replace("<", "").replace(">", "")
    desc = text.replace("<", "").replace(">", "")
    desc += "\n\nTrading psychology · SMC/ICT on gold (XAU/USD). Red days included. 🕯\nInstagram: https://www.instagram.com/ashwal.xau/\nEducation only, not financial advice.\n#Shorts"
    tags = sorted({w.strip("#,.") for w in text.split() if w.startswith("#")} | {"shorts", "xauusd", "trading psychology"})
    return title, desc[:4900], [t for t in tags if t][:15]


def upload(item, privacy):
    title, desc, tags = title_and_description(item["caption"])
    meta = {
        "snippet": {"title": title, "description": desc, "tags": tags, "categoryId": "27",
                    "defaultLanguage": "en", "defaultAudioLanguage": "hi"},
        "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False,
                   "containsSyntheticMedia": True, "embeddable": True},
    }
    path = item.get("yt_media") or item["media"][0]
    size = os.path.getsize(path)
    req = urllib.request.Request(UPLOAD_URL, data=json.dumps(meta).encode(), method="POST", headers={
        "Authorization": "Bearer " + access_token(), "Content-Type": "application/json; charset=UTF-8",
        "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(size)})
    r, _ = http(req)
    location = r.headers["Location"]
    with open(path, "rb") as f:
        put = urllib.request.Request(location, data=f.read(), method="PUT", headers={
            "Authorization": "Bearer " + access_token(), "Content-Type": "video/mp4"})
    _, d = http(put, timeout=900)
    vid = d["id"]
    item["yt_id"] = vid
    item["yt_url"] = "https://youtube.com/shorts/" + vid
    item["yt"] = "posted"
    item["yt_at"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    item.pop("yt_error", None)
    return item["yt_url"]


def pick(items, now, cfg, skip=()):
    """The one reel to upload now, or None. On-time items first, then a slow backlog drip."""
    reels = [i for i in items if i.get("type") == "reel" and i.get("yt", "queued") == "queued" and i["name"] not in skip]
    when = lambda i: datetime.datetime.fromisoformat(i["at"].replace("Z", "+00:00"))
    due = sorted([i for i in reels if when(i) <= now], key=when)
    for i in due:
        if now - when(i) <= ON_TIME:
            return i
    if not due:
        return None
    # Backlog (past reels, or slots missed before YouTube was switched on): one every N hours,
    # never within 1 hour before an upcoming on-time slot.
    gap = datetime.timedelta(hours=float(cfg.get("backlog_gap_hours", 5)))
    last = [datetime.datetime.fromisoformat(i["yt_at"].replace("Z", "+00:00")) for i in items if i.get("yt_at")]
    if last and now - max(last) < gap:
        return None
    upcoming = [when(i) for i in reels if when(i) > now]
    if upcoming and min(upcoming) - now < datetime.timedelta(hours=1):
        return None
    return due[0]


def check():
    import hashlib
    print("token fingerprint:", hashlib.sha256(os.environ["YT_REFRESH_TOKEN"].encode()).hexdigest()[:8])
    d = api("GET", "/channels", part="snippet,statistics", mine="true")
    for c in d.get("items", []):
        print("Channel:", c["snippet"]["title"], "| id", c["id"], "| subs", c["statistics"].get("subscriberCount"))
    if not d.get("items"):
        print("Signed in, but this Google account has no YouTube channel yet.")


def main():
    if "--check" in sys.argv:
        check()
        return 0
    if "--test" in sys.argv:
        # Private test upload of one reel; does not touch schedule.json.
        name = sys.argv[sys.argv.index("--test") + 1]
        privacy = "private"
        if "|" in name:
            name, privacy = name.split("|", 1)
        items = json.load(open("schedule.json", encoding="utf-8"))
        item = dict(next(i for i in items if i["name"] == name))
        url = upload(item, privacy)
        print("Uploaded %s test: %s" % (privacy.upper(), url))
        time.sleep(20)
        v = api("GET", "/videos", part="status", id=item["yt_id"]).get("items", [{}])[0].get("status", {})
        print("YouTube reports privacyStatus=%s uploadStatus=%s" % (v.get("privacyStatus"), v.get("uploadStatus")))
        return 0
    if "--auth-code" in sys.argv:
        # One-time: swap the sign-in code for a refresh token and print it (masked by the workflow).
        code = sys.argv[sys.argv.index("--auth-code") + 1].strip()
        if "code=" in code:
            code = urllib.parse.parse_qs(urllib.parse.urlparse(code).query)["code"][0]
        data = urllib.parse.urlencode(dict(code=code, client_id=os.environ["YT_CLIENT_ID"],
            client_secret=os.environ["YT_CLIENT_SECRET"], redirect_uri="http://localhost",
            grant_type="authorization_code")).encode()
        _, d = http(urllib.request.Request(TOKEN_URL, data=data, method="POST"))
        if "refresh_token" not in d:
            raise SystemExit("No refresh token returned: " + json.dumps({k: v for k, v in d.items() if "token" not in k}))
        print(d["refresh_token"])
        return 0
    if "--auth-url" in sys.argv:
        print("https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(dict(
            client_id=os.environ["YT_CLIENT_ID"], redirect_uri="http://localhost", response_type="code",
            scope="https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly",
            access_type="offline", prompt="consent")))
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
