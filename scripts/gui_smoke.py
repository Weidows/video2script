# -*- coding: utf-8 -*-
"""GUI 端到端联调：起服务 → 上传/预载 → 预览 Range → 跑任务看进度/逐字稿/产物 → reveal。

用法： python scripts/gui_smoke.py [--port 8801] [--model small]
不依赖 pytest，真起 http 服务、真跑一次转写（默认用 samples/say_zh.mp4 + small 模型）。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from _stdio import force_utf8  # noqa: E402

force_utf8()

PORT = 8801
MODEL = "small"
for i, a in enumerate(sys.argv):
    if a == "--port":
        PORT = int(sys.argv[i + 1])
    if a == "--model":
        MODEL = sys.argv[i + 1]
BASE = f"http://127.0.0.1:{PORT}"
SAMPLE = ROOT / "samples" / "say_zh.mp4"
fails: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("  ok   " if ok else "  FAIL ") + name + (f"  [{detail}]" if detail else ""))
    if not ok:
        fails.append(name)


def soft(name: str, ok: bool, detail: str = "") -> None:
    """时序相关的观察项：样本太短时抓不到不算失败，只提示。"""
    print(("  ok   " if ok else "  note ") + name + (f"  [{detail}]" if detail else ""))


def get(path: str, extra_headers: dict | None = None):
    req = urllib.request.Request(BASE + path, headers=extra_headers or {})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


def post(path: str, obj=None, raw: bytes | None = None, ctype="application/json"):
    body = raw if raw is not None else json.dumps(obj or {}).encode()
    req = urllib.request.Request(BASE + path, data=body, method="POST",
                                 headers={"Content-Type": ctype})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def explorer_locations() -> set[str]:
    """当前打开的资源管理器窗口位置（用 COM 查，能真判断"有没有弹窗"）。"""
    ps = ("$sh=New-Object -ComObject Shell.Application;"
          "$sh.Windows() | ForEach-Object { $_.LocationURL }")
    try:
        out = subprocess.run(["pwsh", "-NoProfile", "-Command", ps],
                             capture_output=True, text=True, timeout=60)
        return {ln.strip() for ln in out.stdout.splitlines() if ln.strip()}
    except Exception:
        return set()


def main() -> int:
    assert SAMPLE.exists(), f"缺少样本 {SAMPLE}"
    # -u / PYTHONUNBUFFERED：子进程 stdout 是管道会被块缓冲，不强制无缓冲就抓不到启动那行地址
    env = dict(os.environ, PYTHONUNBUFFERED="1")
    proc = subprocess.Popen([sys.executable, "-u", "-m", "video2script", "--gui",
                             str(SAMPLE), "--port", str(PORT)],
                            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace", env=env)
    out_lines: list[str] = []
    threading.Thread(target=lambda: [out_lines.append(ln.rstrip())
                                     for ln in proc.stdout], daemon=True).start()

    def server_said(pat: str) -> str:
        for ln in out_lines:
            m = re.search(pat, ln)
            if m:
                return m.group(1)
        return ""

    try:
        # 从启动日志里拿预载任务的 id（界面也是靠这个 ?job= 参数预载的）
        preload_id = ""
        for _ in range(60):
            time.sleep(0.5)
            preload_id = server_said(r"job=([0-9a-f]+)")
            if preload_id:
                break
        check("启动日志给出预载 job id", bool(preload_id), preload_id)
        check("启动日志提示已预载", "已预载" in "\n".join(out_lines))
        if not preload_id:
            print("\n".join(out_lines))
            return 1

        print("== 页面与静态资源")
        st, _, body = get("/")
        check("GET / 200", st == 200)
        html = body.decode("utf-8")
        check("页面含预览卡片", 'id="pvbox"' in html)
        check("页面含完整日志面板", 'id="log"' in html and "slice(-8)" not in html)
        check("页面含实时逐字稿", 'id="live"' in html)
        check("页面含进度条", 'class="bar"' in html)
        st, _, body = get("/favicon.ico")
        check("favicon 非空", st == 200 and len(body) > 1000, f"{len(body)}B")

        print("== 预载与预览")
        st, _, body = get("/api/media_info?id=" + preload_id)
        info = json.loads(body)
        check("media_info 有名字/大小", info.get("name") == SAMPLE.name and info.get("size", 0) > 0,
              f"{info.get('name')} {info.get('size')}B")
        st, h, body = get(f"/api/media?id={preload_id}")
        check("整段 GET /api/media 200", st == 200)
        check("Content-Length 与文件一致",
              int(h.get("Content-Length", 0)) == SAMPLE.stat().st_size,
              f"{h.get('Content-Length')}/{SAMPLE.stat().st_size}")
        check("声明支持 Range", h.get("Accept-Ranges") == "bytes")
        st, h, body = get(f"/api/media?id={preload_id}",
                          {"Range": "bytes=0-1023"})
        check("Range 请求返回 206", st == 206, str(st))
        check("Range 返回 1024 字节", len(body) == 1024, f"{len(body)}B")
        check("Content-Range 正确",
              h.get("Content-Range") == f"bytes 0-1023/{SAMPLE.stat().st_size}",
              h.get("Content-Range", ""))

        print("== 上传接口")
        st, up = post("/api/upload?name=" + SAMPLE.name, raw=SAMPLE.read_bytes(),
                      ctype="video/mp4")
        check("上传返回 id/大小", st == 200 and up.get("size") == SAMPLE.stat().st_size,
              str(up.get("size")))
        uid = up.get("id", "")

        print(f"== 跑任务（{MODEL} / level 2 / ass）")
        st, r = post("/api/run", {"id": preload_id, "lang": "zh", "model": MODEL,
                                  "level": 2, "ass": True})
        check("POST /api/run 202/200", st == 200 and r.get("ok"), str(r))

        seen_pct, seen_art, max_partial, log_len = [], 0, 0, 0
        art_during_run = False
        state = "?"
        for _ in range(180):
            time.sleep(2)
            _, _, body = get(f"/api/status?id={preload_id}")
            s = json.loads(body)
            state = s["state"]
            seen_pct.append(s["percent"])
            log_len = max(log_len, len(s["log"]))
            if state == "running" and s["artifacts"]:
                art_during_run = True
            seen_art = max(seen_art, len(s["artifacts"]))
            max_partial = max(max_partial, len(s["partial"]))
            if state in ("done", "error"):
                break
        check("任务完成", state == "done", state)
        check("进度单调不减", seen_pct == sorted(seen_pct),
              f"{seen_pct[0]}..{seen_pct[-1]}")
        check("进度到达 100", seen_pct[-1] >= 100.0, str(seen_pct[-1]))
        soft("跑的过程中就能下到产物（样本短时抓不到）", art_during_run,
             f"{seen_art} 个产物")
        check("实时逐字稿有内容", max_partial > 0, f"{max_partial} 段")
        check("日志完整（>10 行）", log_len > 10, f"{log_len} 行")
        _, _, body = get(f"/api/status?id={preload_id}")
        s = json.loads(body)
        check("clean 稿非空", bool(s["clean_text"]))
        check("文件列表 ≥6", len(s["files"]) >= 6, str(s["files"]))
        check("outdir 存在", Path(s["outdir"]).exists(), s["outdir"])
        for f in s["files"][:3]:
            st, _, b = get(f"/api/file?id={preload_id}&name={f}")
            check(f"下载 {f}", st == 200 and len(b) > 0, f"{len(b)}B")

        print("== 打开输出目录")
        before = explorer_locations()
        st, r = post("/api/reveal", {"id": preload_id})
        check("reveal 返回 ok+path", st == 200 and r.get("ok"), str(r))
        time.sleep(4)
        after = explorer_locations()
        target = Path(s["outdir"]).as_uri()
        check("资源管理器确实打开了该目录", target in after or len(after) > len(before),
              f"new={sorted(after - before)[:2]}")

        print("== 清理")
        st, r = post("/api/run", {"id": "nope"})
        check("未知任务返回 404", st == 404, str(st))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
    print(("\n全部通过 ✅" if not fails else f"\n失败 {len(fails)} 项 ❌: {fails}"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
