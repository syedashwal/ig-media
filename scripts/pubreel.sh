#!/bin/bash
# usage: pubreel.sh <video name in media/> <cover name in media/> <caption file>
v=$1; c=$2; cap=$3
B=https://graph.instagram.com/v21.0; U=17841427007114632; R=https://raw.githubusercontent.com/syedashwal/ig-media/main/media
id=$(curl -s -X POST "$B/$U/media" -d media_type=REELS -d share_to_feed=true --data-urlencode "video_url=$R/$v" --data-urlencode "cover_url=$R/$c" --data-urlencode "caption@$cap" | python3 -c "import sys,json;print(json.load(sys.stdin).get('id',''))")
echo "container $id"
for k in $(seq 1 60); do s=$(curl -s "$B/$id?fields=status_code" | python3 -c "import sys,json;print(json.load(sys.stdin).get('status_code',''))"); echo $s; [ "$s" = FINISHED ] && break; sleep 10; done
r=$(curl -s -X POST "$B/$U/media_publish" -d creation_id=$id); echo "$r"
mid=$(echo "$r" | python3 -c "import sys,json;print(json.load(sys.stdin).get('id',''))")
curl -s "$B/$mid?fields=permalink"
