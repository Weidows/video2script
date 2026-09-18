# -*- coding: utf-8 -*-
"""编排层：CLI / GUI / 库调用都走这一个函数。"""
from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .asr import transcribe
from .clean import smooth
from .config import default_prompt, find_ffmpeg
from .render import build_blocks, cut_video, keep_intervals, to_md, to_srt

LEVELS = (1, 2, 3)
MODELS = ("tiny", "base", "small", "medium", "large-v3")


@dataclass
class Options:
    lang: str = "zh"            # zh / en / auto
    model: str = "small"        # tiny/base/small/medium/large-v3
    device: str = "cpu"         # cpu / cuda
    compute_type: str = "int8"  # int8 / int8_float16 / float16
    level: int = 2              # 顺滑力度 1/2/3
    vad: bool = True
    cut: bool = False           # 额外输出 tight.mp4（需 ffmpeg）
    rewrite: str = "none"       # none / llm
    prompt: str | None = None
    outdir: Path | None = None
    llm_base: str | None = None
    llm_key: str | None = None
    llm_model: str | None = None


@dataclass
class Result:
    outdir: Path
    files: dict[str, Path] = field(default_factory=dict)
    raw_text: str = ""
    clean_text: str = ""
    counts: dict[str, int] = field(default_factory=dict)
    removed: dict[str, list] = field(default_factory=dict)
    language: str = ""
    duration: float = 0.0

    @property
    def kept_seconds(self) -> float:
        return self.duration - 0.0


def emit(cb: Callable | None, kind: str, **data) -> None:
    if cb:
        cb(kind, data)


def llm_rewrite(text: str, opts: Options) -> str:
    """可选的 LLM 兜底：只做最小改动，禁增删信息。"""
    base = opts.llm_base or os.environ.get("V2S_LLM_BASE", "https://api.openai.com/v1")
    key = opts.llm_key or os.environ.get("V2S_LLM_KEY", "")
    model = opts.llm_model or os.environ.get("V2S_LLM_MODEL", "gpt-4o-mini")
    sys_p = ("你是口语转写校对员。输入是已经初步去掉语气词的文稿。要求：只做最小改动——"
             "删除残留的口头禅、结巴、重复词和半截话，补全必要的标点；"
             "不得增删任何信息、不得改写措辞、不得解释。直接输出正文。")
    body = json.dumps({"model": model, "temperature": 0,
                       "messages": [{"role": "system", "content": sys_p},
                                    {"role": "user", "content": text}]}).encode()
    req = urllib.request.Request(base.rstrip("/") + "/chat/completions", body,
                                 {"Content-Type": "application/json",
                                  "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)["choices"][0]["message"]["content"].strip()


def run(video: str | Path, opts: Options | None = None,
        on_event: Callable[[str, dict], None] | None = None) -> Result:
    """完整流程：转写 → 顺滑 → 落盘。``on_event(kind, data)`` 用于 CLI/GUI 报进度。"""
    opts = opts or Options()
    video = Path(video)
    if not video.exists():
        raise FileNotFoundError(f"找不到文件：{video}")

    outdir = Path(opts.outdir) if opts.outdir else Path(str(video.with_suffix(""))
                                                        + "_transcript")
    outdir.mkdir(parents=True, exist_ok=True)
    lang = None if opts.lang == "auto" else opts.lang

    emit(on_event, "stage", stage="asr", message=f"加载模型 {opts.model} …")
    segments, info = transcribe(
        video, model_name=opts.model, lang=lang, device=opts.device,
        compute_type=opts.compute_type,
        prompt=opts.prompt or default_prompt(lang), use_vad=opts.vad,
        on_progress=lambda done, total, text: emit(
            on_event, "progress", stage="asr", done=done, total=total, text=text))

    jt = " " if str(getattr(info, "language", "")).startswith("en") else ""
    raw_text = "\n".join(s.text for s in segments if s.text)
    (outdir / "raw.txt").write_text(raw_text, encoding="utf-8")
    to_srt(build_blocks(segments, max_chars=10 ** 9, max_dur=10 ** 9, max_gap=1.5,
                        jt=jt), outdir / "raw.srt")

    emit(on_event, "stage", stage="clean", message="顺滑处理 …")
    report = smooth(segments, opts.level, lang=str(getattr(info, "language", "zh")))
    clean_text = "\n".join(s.text for s in segments if s.text)
    (outdir / "clean.txt").write_text(clean_text, encoding="utf-8")
    to_srt(build_blocks(segments, jt=jt), outdir / "clean.srt")
    to_md(segments, outdir / "clean.md", jt=jt)

    total = segments[-1].end if segments else 0.0
    counts = {k: len(v) for k, v in report.items()}
    (outdir / "report.json").write_text(json.dumps({
        "input": str(video), "language": getattr(info, "language", ""),
        "model": opts.model, "duration_s": round(total, 2), "level": opts.level,
        "counts": counts, "removed": report,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    files = {n: outdir / n for n in
             ("raw.txt", "raw.srt", "clean.txt", "clean.srt", "clean.md", "report.json")}

    if opts.rewrite == "llm":
        emit(on_event, "stage", stage="llm", message="LLM 通读润色 …")
        (outdir / "clean.llm.txt").write_text(llm_rewrite(clean_text, opts),
                                              encoding="utf-8")
        files["clean.llm.txt"] = outdir / "clean.llm.txt"

    if opts.cut:
        ffmpeg = find_ffmpeg()
        if not ffmpeg:
            emit(on_event, "warn", message="没找到 ffmpeg，跳过 --cut")
        else:
            keeps = keep_intervals(segments, total)
            out = outdir / f"{video.stem}_tight.mp4"
            emit(on_event, "stage", stage="cut",
                 message=f"剪掉被删内容（保留 {len(keeps)} 段 / "
                         f"{sum(e - s for s, e in keeps):.1f}s of {total:.1f}s）…")
            cut_video(video, keeps, out, ffmpeg)
            files[out.name] = out

    res = Result(outdir=outdir, files=files, raw_text=raw_text, clean_text=clean_text,
                 counts=counts, removed=report,
                 language=str(getattr(info, "language", "")), duration=total)
    emit(on_event, "done", result=res)
    return res
