"""Publish due posts from schedule.json to Instagram. Runs from GitHub Actions."""
import json, os, sys, time, datetime, urllib.request, urllib.parse, urllib.error

API = "https://graph.instagram.com/v21.0"
UID = "17841427007114632"
RAW = "https://raw.githubusercontent.com/syedashwal/ig-media/main/"
MAX_LATE = datetime.timedelta(hours=3)
TOKEN = os.environ["IG_TOKEN"]


def call(method, path, **params):
    data = None
    url = API + path
    if method == "POST":
        data = urllib.parse.urlencode(params).encode()
    elif params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, data=data, method=method, headers={"Authorization": "Bearer " + TOKEN})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(e.read().decode())


def wait_finished(cid):
    for _ in range(60):
        st = call("GET", "/" + cid, fields="status_code")
        if st.get("status_code") == "FINISHED":
            return
        if st.get("status_code") in ("ERROR", "EXPIRED"):
            raise RuntimeError("container " + st["status_code"])
        time.sleep(10)
    raise RuntimeError("container not finished in 10 minutes")


def make_container(item, caption):
    kind = item["type"]
    if kind == "image":
        return call("POST", "/%s/media" % UID, image_url=RAW + item["media"][0], caption=caption)["id"]
    if kind == "reel":
        p = dict(media_type="REELS", video_url=RAW + item["media"][0], caption=caption, share_to_feed="true")
        if item.get("cover"):
            p["cover_url"] = RAW + item["cover"]
        return call("POST", "/%s/media" % UID, **p)["id"]
    if kind == "carousel":
        kids = []
        for m in item["media"]:
            c = call("POST", "/%s/media" % UID, image_url=RAW + m, is_carousel_item="true")["id"]
            wait_finished(c)
            kids.append(c)
        return call("POST", "/%s/media" % UID, media_type="CAROUSEL", children=",".join(kids), caption=caption)["id"]
    raise RuntimeError("unknown type " + kind)


def publish(item):
    caption = open(item["caption"], encoding="utf-8").read().strip()
    if not item.get("creation_id"):
        item["creation_id"] = make_container(item, caption)
    wait_finished(item["creation_id"])
    mid = call("POST", "/%s/media_publish" % UID, creation_id=item["creation_id"])["id"]
    item["media_id"] = mid
    item["permalink"] = call("GET", "/" + mid, fields="permalink").get("permalink")
    item["status"] = "posted"


def main():
    if "--check" in sys.argv:
        print(call("GET", "/me", fields="username"))
        return 0
    items = json.load(open("schedule.json", encoding="utf-8"))
    now = datetime.datetime.now(datetime.timezone.utc)
    failed = False
    notes = []
    for item in items:
        if item.get("status", "queued") != "queued":
            continue
        at = datetime.datetime.fromisoformat(item["at"].replace("Z", "+00:00"))
        if at > now:
            continue
        if now - at > MAX_LATE:
            item["status"] = "missed"
            item["error"] = "more than 3 hours late"
            failed = True
            notes.append("MISSED: " + item["name"])
            continue
        try:
            publish(item)
            notes.append("Posted: %s %s" % (item["name"], item["permalink"]))
        except Exception as e:
            item["error"] = str(e)[:300]
            failed = True
            notes.append("FAILED (will retry): %s: %s" % (item["name"], item["error"]))
        json.dump(items, open("schedule.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    json.dump(items, open("schedule.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    if notes:
        open("notes.md", "w").write("\n".join(notes) + "\n")
        print("\n".join(notes))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
