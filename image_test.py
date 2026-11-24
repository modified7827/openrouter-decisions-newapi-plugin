#!/usr/bin/env python3
"""单独测试图像生成:POST /v1/images/generations → 存 image_out.png

用法:
    set NEW_API_BASE=http://localhost:3000
    set NEW_API_KEY=sk-xxx
    python image_test.py "a cat sitting on a windowsill"
"""

import base64
import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("NEW_API_BASE", "http://localhost:3000").rstrip("/")
KEY = os.environ.get("NEW_API_KEY", "")
MODEL = os.environ.get("IMAGE_ALIAS", "Image")
OUT = "image_out.png"

prompt = sys.argv[1] if len(sys.argv) > 1 else "a cat sitting on a windowsill"
if not KEY:
    sys.exit("先设置 NEW_API_KEY")

body = {"model": MODEL, "prompt": prompt, "size": "1024x1024", "n": 1}
req = urllib.request.Request(
    BASE + "/v1/images/generations",
    data=json.dumps(body).encode(),
    headers={
        "Authorization": "Bearer " + KEY,
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 newapi-image-test/1.0",
    },
    method="POST",
)
print("POST %s/v1/images/generations  model=%s  prompt=%r" % (BASE, MODEL, prompt))
try:
    with urllib.request.urlopen(req, timeout=300) as resp:
        payload = json.loads(resp.read())
except urllib.error.HTTPError as e:
    sys.exit("HTTP %d: %s" % (e.code, e.read().decode(errors="replace")[:500]))

data = payload.get("data") or []
first = data[0] if data else {}
if first.get("b64_json"):
    blob = base64.b64decode(first["b64_json"])
elif first.get("url"):
    with urllib.request.urlopen(first["url"], timeout=120) as r:
        blob = r.read()
else:
    sys.exit("响应无 b64_json/url: " + json.dumps(payload, ensure_ascii=False)[:500])

with open(OUT, "wb") as f:
    f.write(blob)
print("saved %s (%d bytes)" % (OUT, len(blob)))
