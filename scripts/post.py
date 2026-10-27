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


def fresh_status(name):
    """Latest status of an item on origin/main (None if unknown), so a post made elsewhere is not repeated."""
    try:
        os.system("git fetch -q origin main")
        out = os.popen("git show origin/main:schedule.json").read()
        for i in json.loads(out):
            if i["name"] == name:
                return i.get("status", "queued")
    except Exception:
        pass
    return None


def already_on_instagram(item):
    """True if a recent post already carries this caption's first line."""
    try:
        head = open(item["caption"], encoding="utf-8").read().strip().split("\n")[0][:40]
        for m in call("GET", "/%s/media" % UID, fields="caption,timestamp", limit=12).get("data", []):
            ts = datetime.datetime.strptime(m["timestamp"], "%Y-%m-%dT%H:%M:%S%z")
            if head and (m.get("caption") or "").startswith(head) and datetime.datetime.now(datetime.timezone.utc) - ts < datetime.timedelta(hours=24):
                item["permalink"] = m.get("permalink")
                return True
    except Exception:
        pass
    return False


def main():
    if "--serve-hours" in sys.argv:
        return serve(float(sys.argv[sys.argv.index("--serve-hours") + 1]))
    if "--check" in sys.argv:
        print(call("GET", "/me", fields="username"))
        return 0
    items = json.load(open("schedule.json", encoding="utf-8"))
    now = datetime.datetime.now(datetime.timezone.utc)
    wait_h = float(sys.argv[sys.argv.index("--wait-hours") + 1]) if "--wait-hours" in sys.argv else 0
    failed = False
    notes = []
    for item in items:
        if item.get("status", "queued") != "queued":
            continue
        at = datetime.datetime.fromisoformat(item["at"].replace("Z", "+00:00"))
        if at > now:
            # Actions cron is slow and irregular: if the slot is close enough, sleep until it so the post lands on time.
            if wait_h and at - now <= datetime.timedelta(hours=wait_h):
                time.sleep(max(0, (at - datetime.datetime.now(datetime.timezone.utc)).total_seconds()))
                st = fresh_status(item["name"])
                if st is not None and st != "queued":
                    item["status"] = st
                    notes.append("Skipped (already %s elsewhere): %s" % (st, item["name"]))
                    continue
                if already_on_instagram(item):
                    item["status"] = "posted"
                    notes.append("Skipped (already live): %s" % item["name"])
                    continue
                now = datetime.datetime.now(datetime.timezone.utc)
            else:
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


def git(*args):
    return os.system("git " + " ".join(args))


def sync():
    git("fetch -q origin main")
    git("reset -q --hard origin/main")


def record(item, notes):
    """Write the item's new state onto the freshest schedule.json and push it, retrying on a race."""
    for _ in range(4):
        sync()
        items = json.load(open("schedule.json", encoding="utf-8"))
        for i in items:
            if i["name"] == item["name"]:
                for k in ("status", "permalink", "media_id", "error"):
                    if k in item:
                        i[k] = item[k]
        json.dump(items, open("schedule.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)
        git('config user.name "github-actions[bot]"')
        git('config user.email "41898299+github-actions[bot]@users.noreply.github.com"')
        git("add schedule.json")
        git('commit -q -m "Update post status: %s"' % item["name"].replace('"', ""))
        if git("push -q origin HEAD:main") == 0:
            break
    if notes:
        open("/tmp/notes.md", "w").write(notes + "\n")
        os.system('gh issue create --title "%s" --body-file /tmp/notes.md || true' % notes.split("\n")[0][:80].replace('"', ""))


def serve(hours):
    """Poll schedule.json on main every ~30s for hours; post each item at its slot. A post made elsewhere is never repeated."""
    deadline = time.time() + hours * 3600
    tries = {}
    while time.time() < deadline:
        sync()
        now = datetime.datetime.now(datetime.timezone.utc)
        for item in json.load(open("schedule.json", encoding="utf-8")):
            if item.get("status", "queued") != "queued":
                continue
            at = datetime.datetime.fromisoformat(item["at"].replace("Z", "+00:00"))
            if at > now or tries.get(item["name"], 0) >= 5:
                continue
            if now - at > MAX_LATE:
                item["status"] = "missed"
                item["error"] = "more than 3 hours late"
                record(item, "MISSED: " + item["name"])
                continue
            tries[item["name"]] = tries.get(item["name"], 0) + 1
            if already_on_instagram(item):
                item["status"] = "posted"
                record(item, "Already live, marked posted: %s %s" % (item["name"], item.get("permalink", "")))
                continue
            try:
                publish(item)
                record(item, "Posted: %s %s" % (item["name"], item["permalink"]))
            except Exception as e:
                item["error"] = str(e)[:300]
                if tries[item["name"]] >= 5:
                    record(item, "FAILED after 5 tries: %s: %s" % (item["name"], item["error"]))
        time.sleep(30)
    return 0


if __name__ == "__main__":
    sys.exit(main())
