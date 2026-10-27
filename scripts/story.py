"""Publish one Story image to Instagram. Usage: story.py media/stories/<file>.jpg"""
import json, os, sys, time, urllib.request, urllib.parse, urllib.error

API = "https://graph.instagram.com/v21.0"
UID = "17841427007114632"
RAW = "https://raw.githubusercontent.com/syedashwal/ig-media/main/"
TOKEN = os.environ["IG_TOKEN"]


def call(method, path, **params):
    url = API + path
    data = urllib.parse.urlencode(params).encode() if method == "POST" else None
    if method == "GET" and params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, data=data, method=method, headers={"Authorization": "Bearer " + TOKEN})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(e.read().decode())


cid = call("POST", "/%s/media" % UID, media_type="STORIES", image_url=RAW + sys.argv[1])["id"]
for _ in range(30):
    st = call("GET", "/" + cid, fields="status_code").get("status_code")
    if st == "FINISHED":
        break
    if st in ("ERROR", "EXPIRED"):
        sys.exit("container " + st)
    time.sleep(5)
mid = call("POST", "/%s/media_publish" % UID, creation_id=cid)["id"]
print("published story", mid)
