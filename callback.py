#!/usr/bin/env python3
"""Gửi kết quả dựng video về webhook Make (callback_url trong job.json).

python callback.py ok   -> gửi link video + thumbnail
python callback.py fail -> gửi thông báo lỗi
"""
import json
import os
import sys
import urllib.request
from pathlib import Path


def main():
    status = sys.argv[1] if len(sys.argv) > 1 else "ok"
    try:
        job = json.loads(Path("job.json").read_text(encoding="utf-8"))
    except Exception:
        job = {}
    url = job.get("callback_url")
    if not url:
        print("Không có callback_url, bỏ qua.")
        return 0

    repo = os.environ.get("GITHUB_REPOSITORY", "")
    run_url = f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/{repo}/actions/runs/{os.environ.get('GITHUB_RUN_ID', '')}"
    body = {"ok": status == "ok", "job_id": job.get("job_id"), "run_url": run_url,
            "meta": job.get("meta", {})}
    if status == "ok":
        tag = os.environ["TAG"]
        base = f"https://github.com/{repo}/releases/download/{tag}"
        result = json.loads(Path("out/result.json").read_text(encoding="utf-8"))
        body.update({"video_url": f"{base}/short.mp4", "thumb_url": f"{base}/thumbnail.jpg",
                     "duration": result.get("duration"), "size_mb": result.get("size_mb")})
    else:
        body["error"] = "GitHub Actions dựng video thất bại, xem chi tiết ở run_url"

    req = urllib.request.Request(url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        print("Make trả về:", r.status)
    return 0


if __name__ == "__main__":
    sys.exit(main())
