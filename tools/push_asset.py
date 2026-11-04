# -*- coding: utf-8 -*-
"""上传 Release 资产（先删同名旧资产，再传新文件）。

用法：python tools/push_asset.py <file> [<file> ...]
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

TOKEN = os.environ.get("GH_TOKEN", "")
OWNER, REPO = "mew5748-alt", "PicSprite"
TAG = "v1.0.0"
API = "https://api.github.com"


def req(method: str, url: str, data=None, ctype: str = "application/json"):
    headers = {
        "Authorization": "Bearer " + TOKEN,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "PicSprite-release",
    }
    body = None
    if data is not None:
        if isinstance(data, (dict, list)):
            body = json.dumps(data).encode()
        else:
            body = data
            headers["Content-Type"] = ctype
    r = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=900) as resp:
            return resp.status, _parse(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, _parse(e.read())


def _parse(raw: bytes):
    """空响应（如 DELETE 的 204）返回 None，其余尽量解析成 JSON。"""
    if not raw:
        return None
    if raw.lstrip()[:1] in (b"{", b"["):
        try:
            return json.loads(raw)
        except Exception:
            pass
    return raw[:300]


def release_id() -> int:
    code, d = req("GET", f"{API}/repos/{OWNER}/{REPO}/releases/tags/{TAG}")
    if code != 200:
        raise SystemExit(f"取 Release 失败 {code}: {d}")
    return d["id"]


def main() -> int:
    if not TOKEN:
        raise SystemExit("缺少 GH_TOKEN")
    rid = release_id()
    print(f"release id = {rid}")

    # 现有资产
    code, assets = req("GET", f"{API}/repos/{OWNER}/{REPO}/releases/{rid}/assets")
    if code != 200:
        raise SystemExit(f"取资产列表失败 {code}: {assets}")
    existing = {a["name"]: a["id"] for a in assets}
    print("现有资产:", list(existing) or "无")

    for arg in sys.argv[1:]:
        # 支持 "本地路径=远端文件名"，中文文件名传上去容易出问题
        path, _, remote = arg.partition("=")
        name = remote or os.path.basename(path)
        if not os.path.isfile(path):
            print(f"跳过（不存在）: {path}")
            continue
        size = os.path.getsize(path)
        if name in existing:
            c, _ = req("DELETE",
                       f"{API}/repos/{OWNER}/{REPO}/releases/assets/{existing[name]}")
            print(f"  删除旧 {name}: {c}")
        print(f"  上传 {name} ({size / 1024 / 1024:.1f} MB) …", flush=True)
        with open(path, "rb") as f:
            payload = f.read()
        url = (f"https://uploads.github.com/repos/{OWNER}/{REPO}/releases/"
               f"{rid}/assets?name={urllib.parse.quote(name)}")
        c, d = req("POST", url, payload, "application/octet-stream")
        if c in (200, 201):
            print(f"  OK  {d['name']}  {d['size'] / 1024 / 1024:.1f} MB  {d['state']}")
            print("      " + d["browser_download_url"])
        else:
            print(f"  失败 {c}: {d}")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
