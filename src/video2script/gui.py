# -*- coding: utf-8 -*-
"""零依赖本地网页 GUI：``video2script-gui``

只用 Python 标准库（http.server）起一个本地服务，浏览器打开就是界面：
拖入视频 → 选参数 → 跑 → 逐字稿/清洗稿左右对照 + 下载产物。
不上传任何云端，全部在本机跑。
"""
from __future__ import annotations

import json
import re
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

PAGE = r"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>video2script · 视频转文稿</title>
<link rel="icon" href="/favicon.ico">
<link rel="apple-touch-icon" href="/icon.png">
<style>
 *{box-sizing:border-box}
 body{margin:0;font:14px/1.6 system-ui,"Microsoft YaHei",sans-serif;
      background:#0f1115;color:#e6e8ee}
 header{padding:18px 24px;border-bottom:1px solid #23262f;display:flex;gap:12px;
        align-items:baseline}
 header h1{font-size:17px;margin:0}
 header span{color:#8b93a7;font-size:12px}
 main{max-width:1100px;margin:0 auto;padding:24px;display:grid;gap:20px}
 .card{background:#161922;border:1px solid #23262f;border-radius:10px;padding:18px}
 #drop{border:2px dashed #333a49;border-radius:10px;padding:34px;text-align:center;
       color:#8b93a7;cursor:pointer;transition:.15s}
 #drop.hot{border-color:#4f8cff;background:#182034;color:#cfe0ff}
 #drop b{color:#e6e8ee}
 .opts{display:flex;flex-wrap:wrap;gap:14px;margin-top:16px;align-items:flex-end}
 label{display:flex;flex-direction:column;gap:4px;font-size:12px;color:#8b93a7}
 select,input[type=text]{background:#0f1115;color:#e6e8ee;border:1px solid #2c313d;
       border-radius:6px;padding:7px 9px;font:inherit;font-size:13px;min-width:130px}
 button{background:#4f8cff;color:#fff;border:0;border-radius:7px;padding:9px 18px;
        font:inherit;font-weight:600;cursor:pointer}
 button.sec{background:#232a38;font-weight:500}
 button:disabled{opacity:.45;cursor:not-allowed}
 #bar{height:7px;background:#23262f;border-radius:99px;overflow:hidden;margin:14px 0 6px}
 #bar>i{display:block;height:100%;width:0;background:#4f8cff;transition:.3s}
 #log{font:12px/1.7 ui-monospace,Consolas,monospace;color:#8b93a7;white-space:pre-wrap;
      max-height:130px;overflow:auto}
 .cols{display:grid;grid-template-columns:1fr 1fr;gap:16px}
 textarea{width:100%;height:260px;background:#0f1115;color:#e6e8ee;border:1px solid #2c313d;
          border-radius:8px;padding:12px;font:13px/1.8 ui-monospace,Consolas,monospace;
          resize:vertical}
 .tag{display:inline-block;background:#232a38;color:#a8b3c9;border-radius:5px;
      padding:2px 8px;font-size:12px;margin:0 6px 6px 0}
 .files a{display:inline-block;margin:0 10px 8px 0;color:#7fb0ff;text-decoration:none}
 .files a:hover{text-decoration:underline}
 .err{color:#ff8f8f}
 h3{margin:0 0 10px;font-size:14px;font-weight:600;color:#c7cede}
</style></head><body>
<header><h1>video2script</h1><span>视频 → 文稿，自动剔除语气词 / 结巴 / 重复词（全部本机运行，v__VER__）</span></header>
<main>
  <div class="card">
    <div id="drop">把视频/音频文件<b>拖到这里</b>，或点击选择文件<br><span id="fname"></span></div>
    <div class="opts">
      <label>语言<select id="lang">
        <option value="zh" selected>中文</option><option value="en">English</option>
        <option value="auto">自动识别</option></select></label>
      <label>模型<select id="model">
        <option value="small">small（快，中文易错）</option>
        <option value="medium" selected>medium（推荐）</option>
        <option value="large-v3">large-v3（最准，最慢）</option>
        <option value="base">base</option><option value="tiny">tiny</option></select></label>
      <label>顺滑力度<select id="level">
        <option value="1">1 · 只删语气词</option>
        <option value="2" selected>2 · 推荐</option>
        <option value="3">3 · 激进</option></select></label>
      <label>额外输出<select id="extras">
        <option value="">无</option>
        <option value="cut">剪掉语气词的 tight.mp4</option>
        <option value="llm">再用 LLM 润色（需 key）</option></select></label>
      <label>设备<select id="device">
        <option value="cpu" selected>CPU</option><option value="cuda">CUDA</option></select></label>
      <label>字幕<select id="subs">
        <option value="">无</option>
        <option value="ass">导出 clean.ass</option>
        <option value="burn">烧进画面（需 ffmpeg）</option></select></label>
      <label>说话人<select id="diar">
        <option value="0">不区分</option>
        <option value="1">分离说话人（首次下 35MB 模型）</option></select></label>
      <button id="go" disabled>开始转写</button>
    </div>
    <div id="bar"><i></i></div>
    <div id="log">等待上传文件 …</div>
  </div>
  <div class="card" id="result" style="display:none">
    <h3>结果 <span id="meta" class="tag"></span></h3>
    <div id="counts" style="margin-bottom:10px"></div>
    <div class="files" id="files"></div>
    <div class="cols">
      <div><h3>逐字稿（raw）</h3><textarea id="raw" readonly></textarea></div>
      <div><h3>清洗稿（clean）</h3><textarea id="clean" readonly></textarea></div>
    </div>
    <div style="margin-top:12px"><button class="sec" id="reveal">打开输出目录</button></div>
  </div>
</main>
<script>
let job=null, timer=null;
const $=id=>document.getElementById(id);
const drop=$('drop');
drop.onclick=()=>{const i=document.createElement('input');i.type='file';i.onchange=()=>i.files[0]&&up(i.files[0]);i.click()};
['dragenter','dragover'].forEach(e=>drop.addEventListener(e,ev=>{ev.preventDefault();drop.classList.add('hot')}));
['dragleave','drop'].forEach(e=>drop.addEventListener(e,ev=>{ev.preventDefault();drop.classList.remove('hot')}));
drop.addEventListener('drop',ev=>{const f=ev.dataTransfer.files[0];if(f)up(f)});
async function up(file){
  $('fname').textContent='上传中：'+file.name;
  $('log').textContent='正在把文件交给本地服务 …';
  const r=await fetch('/api/upload?name='+encodeURIComponent(file.name),{method:'POST',body:file});
  const j=await r.json();
  if(!r.ok){$('log').textContent='上传失败：'+(j.error||r.status);return}
  job=j.id; $('fname').textContent='已选择：'+file.name; $('go').disabled=false;
  $('log').textContent='准备就绪，点「开始转写」。';
}
// 由 `video2script --gui 文件.mp4` 预载的任务：?job=<id>
(async function(){
  const pre=new URLSearchParams(location.search).get('job');
  if(!pre)return;
  const r=await fetch('/api/status?id='+pre);
  if(!r.ok)return;
  const s=await r.json();
  job=pre; $('go').disabled=false;
  $('fname').textContent='已载入：'+(s.log&&s.log[0]?s.log[0].replace(/^已接收\s*/,''):pre);
  $('log').textContent='文件已就绪，选好参数点「开始转写」。';
})();
$('go').onclick=async()=>{
  if(!job)return;
  $('go').disabled=true; $('result').style.display='none';
  const body={id:job,lang:$('lang').value,model:$('model').value,level:+$('level').value,
              device:$('device').value,cut:$('extras').value==='cut',
              rewrite:$('extras').value==='llm'?'llm':'none',
              diarize:$('diar').value==='1',
              ass:$('subs').value==='ass', burn:$('subs').value==='burn'};
  const r=await fetch('/api/run',{method:'POST',body:JSON.stringify(body)});
  if(!r.ok){$('log').textContent='启动失败';$('go').disabled=false;return}
  timer=setInterval(poll,1000);
};
async function poll(){
  const r=await fetch('/api/status?id='+job); const s=await r.json();
  document.querySelector('#bar>i').style.width=(s.percent||0)+'%';
  $('log').textContent=(s.log||[]).slice(-8).join('\n')||'';
  if(s.state==='error'){$('log').innerHTML='<span class="err">'+(s.error||'失败')+'</span>';
    $('go').disabled=false;clearInterval(timer);return}
  if(s.state==='done'){
    clearInterval(timer); $('go').disabled=false;
    $('result').style.display='block';
    $('raw').value=s.raw_text||''; $('clean').value=s.clean_text||'';
    $('meta').textContent=s.language+' · '+s.duration.toFixed(1)+'s · '+s.model;
    $('counts').innerHTML=Object.entries(s.counts||{}).map(([k,v])=>`<span class="tag">${k} ${v}</span>`).join('');
    $('files').innerHTML=(s.files||[]).map(f=>`<a href="/api/file?id=${job}&name=${encodeURIComponent(f)}">⬇ ${f}</a>`).join('');
  }
}
$('reveal').onclick=()=>fetch('/api/reveal',{method:'POST',body:JSON.stringify({id:job})});
</script></body></html>
"""


# ---------------------------------------------------------------- 任务管理
class Job:
    def __init__(self, jid: str, video: Path, outdir: Path):
        self.id = jid
        self.video = video
        self.outdir = outdir
        self.state = "new"             # new / queued / running / done / error
        self.log: list[str] = []
        self.percent = 0.0
        self.error = ""
        self.result: Result | None = None
        self.model = ""

    def add(self, line: str) -> None:
        self.log.append(line)
        del self.log[:-200]

    def snapshot(self) -> dict:
        r = self.result
        return {
            "state": self.state, "percent": round(self.percent, 1),
            "log": self.log, "error": self.error, "model": self.model,
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
            except Exception as e:  # 单任务失败不影响服务
                job.state, job.error = "error", f"{type(e).__name__}: {e}"
                job.add(f"错误：{job.error}")
    threading.Thread(target=work, daemon=True).start()


def _on_event(job: Job, kind: str, d: dict) -> None:
    if kind == "stage":
        job.add(f"[{d['stage']}] {d['message']}")
    elif kind == "warn":
        job.add(f"! {d['message']}")
    elif kind == "progress":
        job.model = job.model
        total = d.get("total") or 0
        job.percent = (d["done"] / total * 100) if total else min(95.0, job.percent + 0.5)
        if d.get("text"):
            job.add(f"  {d['text'][:60]}")


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
        if u.path in ("/", "/index.html"):
            return self._send(200, PAGE.replace("__VER__", __version__).encode(),
                              "text/html; charset=utf-8")
        if u.path in self.ASSETS:
            return self._serve_asset(u.path)
        if u.path == "/api/status":
            jid = (parse_qs(u.query).get("id") or [""])[0]
            job = JOBS.get(jid)
            if not job:
                return self._json({"error": "unknown job"}, 404)
            with JOBS_LOCK:
                return self._json(job.snapshot())
        if u.path == "/api/file":
            q = parse_qs(u.query)
            jid, name = (q.get("id") or [""])[0], (q.get("name") or [""])[0]
            job = JOBS.get(jid)
            if not job or not job.result:
                return self._json({"error": "not ready"}, 404)
            safe = Path(name).name
            f = (job.result.outdir / safe).resolve()
            if f.parent != job.result.outdir.resolve() or not f.exists():
                return self._json({"error": "no such file"}, 404)
            ctype = "text/plain; charset=utf-8" if f.suffix != ".mp4" else "video/mp4"
            return self._send(200, f.read_bytes(), ctype,
                              {"Content-Disposition": f'attachment; filename="{safe}"'})
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
            return self._json({"id": jid, "name": name})

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
            job.state, job.percent, job.log, job.result = "queued", 0.0, [], None
            start_job(job, opts)
            return self._json({"ok": True})

        if u.path == "/api/reveal":
            try:
                d = json.loads(self._body() or b"{}")
            except json.JSONDecodeError:
                d = {}
            job = JOBS.get(d.get("id", ""))
            target = job.result.outdir if job and job.result else None
            if target and target.exists():
                open_folder(target)
                return self._json({"ok": True, "path": str(target)})
            return self._json({"error": "还没有输出"}, 404)

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
