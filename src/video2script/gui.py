# -*- coding: utf-8 -*-
"""零依赖本地网页 GUI：``video2script --gui``（等价入口 ``video2script-gui``）

只用 Python 标准库（http.server）起一个本地服务，浏览器打开就是界面：
拖入视频 → 预览卡片 → 选参数 → 实时看逐字稿/日志/进度 → 下载产物。
不上传任何云端，全部在本机跑。
"""
from __future__ import annotations

import json
import mimetypes
import re
import sys
import threading
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import __version__
from .config import ASSETS_DIR, force_utf8_stdio, open_folder
from .pipeline import LEVELS, MODELS, Options, Result, run

# 同一时间只跑一个转写任务（CPU 推理本来就吃满核心）
JOB_LOCK = threading.Semaphore(1)
JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()
WORKDIR = Path.home() / ".cache" / "video2script" / "jobs"
MAX_LOG_LINES = 20000

VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".flv", ".ts", ".wmv", ".mpg",
             ".mpeg", ".3gp"}
AUDIO_EXT = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma", ".amr"}


# ---------------------------------------------------------------- 页面
_PAGE_TEMPLATE: str
try:
    _PAGE_TEMPLATE = (ASSETS_DIR / "gui.html").read_text(encoding="utf-8")
except OSError:                        # 资源缺失也不能 500，给个可读提示
    _PAGE_TEMPLATE = ("<meta charset='utf-8'><h1>video2script</h1>"
                      "<p>缺少 assets/gui.html：请从完整仓库安装（pip install -e .），"
                      "或运行 <code>python -m video2script --gui</code> 时确认 assets 目录存在。</p>")

# 兼容旧引用（CI 会检查这个属性）
PAGE = _PAGE_TEMPLATE


def render_page() -> bytes:
    return _PAGE_TEMPLATE.replace("{{VERSION}}", __version__).encode("utf-8")


# ---------------------------------------------------------------- 任务管理
class Job:
    def __init__(self, jid: str, video: Path, outdir: Path):
        self.id = jid
        self.video = video
        self.outdir = outdir
        self.state = "new"             # new / queued / running / done / error
        self.stage = "等待开始"
        self.log: list[str] = []
        self.partial: list[str] = []   # 实时逐字稿（每段一行）
        self.artifacts: list[str] = []  # 已写出的产物名（按写出顺序）
        self.percent = 0.0
        self.error = ""
        self.result: Result | None = None
        self.model = ""
        self._pct_logged = -1

    def add(self, line: str) -> None:
        self.log.append(line)
        if len(self.log) > MAX_LOG_LINES:
            del self.log[:len(self.log) - MAX_LOG_LINES]

    def maybe_log_progress(self) -> None:
        """进度每跨过 5% 记一行日志，既能看出在动，又不刷屏。"""
        step = int(self.percent // 5)
        if step > self._pct_logged:
            self._pct_logged = step
            if step and step % 2 == 0:      # 每 10% 一条
                self.add(f"  … 已处理 {self.percent:.0f}%")

    def snapshot(self) -> dict:
        r = self.result
        return {
            "state": self.state, "stage": self.stage,
            "percent": round(self.percent, 1),
            "log": self.log, "error": self.error, "model": self.model,
            "partial": self.partial,
            "artifacts": self.artifacts,
            "language": r.language if r else "", "duration": r.duration if r else 0.0,
            "counts": r.counts if r else {}, "raw_text": r.raw_text if r else "",
            "clean_text": r.clean_text if r else "",
            "files": [p.name for p in r.files.values()] if r else [],
            "outdir": str(self.outdir),
        }


def start_job(job: Job, opts: Options) -> None:
    def work():
        with JOB_LOCK:
            job.state = "running"
            try:
                res = run(job.video, opts, on_event=lambda kind, d: _on_event(job, kind, d))
                job.result, job.state, job.percent = res, "done", 100.0
                job.stage = "完成"
            except Exception as e:  # 单任务失败不影响服务
                job.state, job.error = "error", f"{type(e).__name__}: {e}"
                job.stage = "失败"
                job.add(f"错误：{job.error}")
    threading.Thread(target=work, daemon=True).start()


def _on_event(job: Job, kind: str, d: dict) -> None:
    if kind == "stage":
        job.stage = str(d.get("message") or d.get("stage", ""))
        job.add(f"[{d.get('stage', '')}] {d.get('message', '')}")
        if "percent" in d:
            job.percent = float(d["percent"])
    elif kind == "progress":
        if "percent" in d:
            job.percent = float(d["percent"])
        job.maybe_log_progress()
        text = (d.get("text") or "").strip()
        if text and (not job.partial or job.partial[-1] != text):
            job.partial.append(text)
    elif kind == "artifact":
        name = str(d.get("name", ""))
        if name and name not in job.artifacts:
            job.artifacts.append(name)
            job.add(f"  ✔ 写出 {name}")
    elif kind == "warn":
        job.add(f"! {d.get('message', '')}")
    elif kind == "done":
        job.percent, job.stage = 100.0, "完成"


# ---------------------------------------------------------------- 工具
def parse_range(header: str | None, size: int) -> tuple[int, int] | None:
    """解析 HTTP Range 头（``bytes=start-end``）→ 闭区间；非法/缺失返回 None。

    浏览器播放 <video> 要拖进度条，必须支持 Range，否则只能顺放。
    """
    if not header or size <= 0:
        return None
    m = re.match(r"bytes=(\d*)-(\d*)$", header.strip())
    if not m:
        return None
    s, e = m.group(1), m.group(2)
    if s == "" and e == "":                       # bytes=-
        return None
    if s == "":                                   # bytes=-500 最后 500 字节
        n = int(e)
        return (max(0, size - n), size - 1)
    start = int(s)
    end = int(e) if e else size - 1
    if start >= size:
        return None
    return (start, min(end, size - 1))


def media_info(job: Job) -> dict:
    st = job.video
    return {"id": job.id, "name": st.name, "size": st.stat().st_size if st.exists() else 0,
            "path": str(st)}

# ---------------------------------------------------------------- HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = "video2script/" + __version__

    def log_message(self, *a):  # 静音 access log
        pass

    # ---- helpers
    def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode(),
                   "application/json; charset=utf-8")

    def _body(self) -> bytes:
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def _stream_file(self, path: Path, ctype: str, download: str | None = None):
        """带 Range 的静态文件服务（视频预览要能拖进度条）。"""
        size = path.stat().st_size
        rng = parse_range(self.headers.get("Range"), size)
        start, end = rng if rng else (0, size - 1)
        length = max(0, end - start + 1)
        self.send_response(206 if rng else 200)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if rng:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        if download:
            self.send_header("Content-Disposition", f'attachment; filename="{download}"')
        self.end_headers()
        with path.open("rb") as f:
            f.seek(start)
            left = length
            while left > 0:
                chunk = f.read(min(1 << 20, left))
                if not chunk:
                    break
                self.wfile.write(chunk)
                left -= len(chunk)

    def _resolve_out_file(self, jid: str, name: str) -> Path | None:
        job = JOBS.get(jid)
        if not job or not job.result:
            return None
        safe = Path(name).name
        f = (job.result.outdir / safe).resolve()
        if f.parent != job.result.outdir.resolve() or not f.exists():
            return None
        return f

    # ---- routes
    ASSETS = {"/favicon.ico": ("icon.ico", "image/x-icon"),
              "/icon.png": ("icon.png", "image/png"),
              "/icon-32.png": ("icon-32.png", "image/png"),
              "/icon-16.png": ("icon-16.png", "image/png")}

    def _serve_asset(self, path: str):
        name, ctype = self.ASSETS[path]
        f = ASSETS_DIR / name
        if not f.exists():                      # 源码运行且没生成图标时不该 500
            return self._json({"error": "icon not generated"}, 404)
        return self._send(200, f.read_bytes(), ctype, {"Cache-Control": "max-age=86400"})

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path in ("/", "/index.html"):
            return self._send(200, render_page(), "text/html; charset=utf-8")
        if u.path in self.ASSETS:
            return self._serve_asset(u.path)

        if u.path == "/api/status":
            job = JOBS.get((q.get("id") or [""])[0])
            if not job:
                return self._json({"error": "unknown job"}, 404)
            with JOBS_LOCK:
                return self._json(job.snapshot())

        if u.path == "/api/media_info":         # 预载任务用：拿到文件名/大小/时长
            job = JOBS.get((q.get("id") or [""])[0])
            if not job:
                return self._json({"error": "unknown job"}, 404)
            return self._json(media_info(job))

        if u.path == "/api/media":              # 预览播放源（视频/音频本体）
            job = JOBS.get((q.get("id") or [""])[0])
            if not job or not job.video.exists():
                return self._json({"error": "no media"}, 404)
            ext = job.video.suffix.lower()
            ctype = mimetypes.guess_type(job.video.name)[0] or (
                "video/mp4" if ext in VIDEO_EXT else "audio/wav")
            return self._stream_file(job.video, ctype)

        if u.path == "/api/file":
            jid, name = (q.get("id") or [""])[0], (q.get("name") or [""])[0]
            f = self._resolve_out_file(jid, name)
            if not f:
                return self._json({"error": "no such file"}, 404)
            ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
            if f.suffix in (".txt", ".srt", ".md", ".ass", ".json"):
                ctype = "text/plain; charset=utf-8"
            return self._stream_file(f, ctype, download=f.name)

        return self._json({"error": "not found"}, 404)

    def do_POST(self):
        u = urlparse(self.path)
        if u.path == "/api/upload":
            name = Path(unquote((parse_qs(u.query).get("name") or ["upload.mp4"])[0])).name
            if not name:
                name = "upload.mp4"
            jid = uuid.uuid4().hex[:12]
            dest = WORKDIR / jid
            (dest / "uploads").mkdir(parents=True, exist_ok=True)
            video = dest / "uploads" / name
            # 必须按 Content-Length 精确读完；否则 keep-alive 连接上再 read 会永久阻塞
            remaining = int(self.headers.get("Content-Length") or 0)
            with video.open("wb") as f:
                while remaining > 0:
                    chunk = self.rfile.read(min(1 << 20, remaining))
                    if not chunk:
                        break
                    f.write(chunk)
                    remaining -= len(chunk)
            job = Job(jid, video, dest / (video.stem + "_transcript"))
            with JOBS_LOCK:
                JOBS[jid] = job
            job.add(f"已接收 {name}（{video.stat().st_size / 1e6:.1f} MB）")
            return self._json(media_info(job))

        if u.path == "/api/run":
            try:
                d = json.loads(self._body() or b"{}")
            except json.JSONDecodeError:
                return self._json({"error": "bad json"}, 400)
            job = JOBS.get(d.get("id", ""))
            if not job:
                return self._json({"error": "unknown job"}, 404)
            if job.state in ("running", "queued"):
                return self._json({"error": "该任务已在运行"}, 409)
            lvl = int(d.get("level", 2))
            job.model = str(d.get("model", "medium"))
            opts = Options(lang=str(d.get("lang", "zh")), model=job.model,
                           level=lvl if lvl in LEVELS else 2,
                           device=str(d.get("device", "cpu")),
                           compute_type=str(d.get("compute_type", "int8")),
                           cut=bool(d.get("cut")), rewrite=str(d.get("rewrite", "none")),
                           diarize=bool(d.get("diarize")),
                           num_speakers=int(d.get("num_speakers", -1) or -1),
                           ass=bool(d.get("ass")), burn=bool(d.get("burn")),
                           outdir=job.outdir)
            if opts.model not in MODELS:
                opts.model = "small"
            job.state, job.percent, job.stage = "queued", 0.0, "排队中"
            job.log, job.partial, job.artifacts = [], [], []
            job.result, job.error, job._pct_logged = None, "", -1
            start_job(job, opts)
            return self._json({"ok": True})

        if u.path == "/api/reveal":
            try:
                d = json.loads(self._body() or b"{}")
            except json.JSONDecodeError:
                d = {}
            job = JOBS.get(d.get("id", ""))
            target = job.result.outdir if job and job.result else None
            if not target or not target.exists():
                return self._json({"error": "还没有输出目录"}, 404)
            try:
                open_folder(target)
            except Exception as e:              # 桌面环境缺失时给出明确原因
                return self._json({"error": f"{type(e).__name__}: {e}",
                                   "path": str(target)}, 500)
            return self._json({"ok": True, "path": str(target)})

        return self._json({"error": "not found"}, 404)


def main(argv: list[str] | None = None) -> int:
    import argparse

    force_utf8_stdio()
    ap = argparse.ArgumentParser(prog="video2script-gui",
                                 description="video2script 的本地网页界面"
                                             "（等价于 `video2script --gui`）")
    ap.add_argument("video", nargs="?", type=Path,
                    help="可选：启动后把这个文件预载进界面")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8756)
    ap.add_argument("--open", action="store_true", help="启动后自动打开浏览器")
    a = ap.parse_args(argv)

    WORKDIR.mkdir(parents=True, exist_ok=True)

    # --gui <文件> 时把文件直接注册成待跑任务，界面上就不用再拖一次
    preload = ""
    if a.video:
        if not a.video.exists():
            print(f"! 找不到文件：{a.video}", file=sys.stderr)
        else:
            v = a.video.resolve()
            jid = uuid.uuid4().hex[:12]
            job = Job(jid, v, Path(str(v.with_suffix("")) + "_transcript"))
            with JOBS_LOCK:
                JOBS[jid] = job
            job.add(f"已接收 {v.name}（{v.stat().st_size / 1e6:.1f} MB，命令行预载）")
            preload = f"?job={jid}"

    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    url = f"http://{a.host}:{a.port}/{preload}"
    print(f"video2script GUI on {url}  (Ctrl+C 退出)")
    print(f"任务目录：{WORKDIR}")
    if a.video and preload:
        print(f"已预载：{a.video}  → 在页面上选参数后点「开始转写」")
    if a.open:
        threading.Thread(target=lambda: (time.sleep(0.6), webbrowser.open(url)),
                         daemon=True).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n再见")
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
