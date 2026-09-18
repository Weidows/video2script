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
    diarize: bool = False       # 说话人分离（需 sherpa-onnx）
    num_speakers: int = -1      # -1 = 自动判断人数
    diar_threshold: float = 0.5
    ass: bool = False           # 输出 clean.ass
    burn: bool = False          # 把字幕烧进画面（需 ffmpeg）
    ass_font: str = "Microsoft YaHei"


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
    speakers: dict[str, int] = field(default_factory=dict)

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


# GUI 进度条的阶段预算（百分比），保证"一直在动"而不是长时间停在 0%
PCT = {"start": 1.0, "asr": 80.0, "clean": 84.0, "diar": 92.0,
       "render": 96.0, "ass": 98.0, "llm": 98.5, "burn": 99.0, "cut": 99.5,
       "done": 100.0}


def stage_pct(name: str) -> float:
    return PCT.get(name, 0.0)


def _emit_stage(on_event, stage: str, message: str) -> None:
    emit(on_event, "stage", stage=stage, message=message, percent=stage_pct(stage))


def _save_text(path: Path, text: str, on_event) -> None:
    """写文件并立刻向 GUI 宣告"这个产物出来了"，界面就能边跑边下载。"""
    path.write_text(text, encoding="utf-8")
    emit(on_event, "artifact", name=path.name)


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

    _emit_stage(on_event, "start", f"加载模型 {opts.model}（首次运行需下载权重）…")

    def asr_progress(done: float, total: float, text: str) -> None:
        frac = min(1.0, done / total) if total else 0.0
        emit(on_event, "progress", stage="asr", done=done, total=total, text=text,
             percent=stage_pct("start") + (stage_pct("asr") - stage_pct("start")) * frac)

    segments, info = transcribe(
        video, model_name=opts.model, lang=lang, device=opts.device,
        compute_type=opts.compute_type,
        prompt=opts.prompt or default_prompt(lang), use_vad=opts.vad,
        on_progress=asr_progress)

    jt = " " if str(getattr(info, "language", "")).startswith("en") else ""
    raw_text = "\n".join(s.text for s in segments if s.text)
    _save_text(outdir / "raw.txt", raw_text, on_event)
    to_srt(build_blocks(segments, max_chars=10 ** 9, max_dur=10 ** 9, max_gap=1.5,
                        jt=jt), outdir / "raw.srt")
    emit(on_event, "artifact", name="raw.srt")

    _emit_stage(on_event, "clean", "顺滑处理：剔除语气词 / 结巴 / 重复词 …")
    report = smooth(segments, opts.level, lang=str(getattr(info, "language", "zh")))

    # 说话人分离（可选）：必须在顺滑之后，因为要按"保留下来的内容"贴标签
    speakers: dict[str, int] = {}
    if opts.diarize:
        from .config import DEFAULT_MODEL_DIR
        from .diarize import assign_speakers, diarize
        _emit_stage(on_event, "diar", "说话人分离（首次运行需下载 ~35MB 模型）…")
        turns = diarize(video, Path(os.environ.get("V2S_DIAR_DIR")
                                    or DEFAULT_MODEL_DIR / "diar"),
                        num_speakers=opts.num_speakers, threshold=opts.diar_threshold,
                        workdir=outdir, on_event=on_event)
        speakers = assign_speakers(segments, turns)
        _save_text(outdir / "speakers.json", json.dumps(
            {"turns": [t.__dict__ for t in turns], "segment_counts": speakers},
            ensure_ascii=False, indent=2), on_event)

    clean_text = "\n".join(s.text for s in segments if s.text)
    _save_text(outdir / "clean.txt", clean_text, on_event)
    _emit_stage(on_event, "render", "生成字幕与分段稿 …")
    clean_blocks = build_blocks(segments, jt=jt)
    to_srt(clean_blocks, outdir / "clean.srt")
    to_md(segments, outdir / "clean.md", jt=jt)
    emit(on_event, "artifact", name="clean.srt")
    emit(on_event, "artifact", name="clean.md")

    if opts.diarize:
        from .clean import speaker_prefix
        clean_text = "\n".join((speaker_prefix(s) + s.text) if s.speaker else s.text
                               for s in segments if s.text)
        _save_text(outdir / "clean.txt", clean_text, on_event)

    total = segments[-1].end if segments else 0.0
    counts = {k: len(v) for k, v in report.items()}
    _save_text(outdir / "report.json", json.dumps({
        "input": str(video), "language": getattr(info, "language", ""),
        "model": opts.model, "duration_s": round(total, 2), "level": opts.level,
        "counts": counts, "removed": report,
    }, ensure_ascii=False, indent=2), on_event)

    files = {n: outdir / n for n in
             ("raw.txt", "raw.srt", "clean.txt", "clean.srt", "clean.md", "report.json")}
    if opts.diarize:
        files["speakers.json"] = outdir / "speakers.json"

    # 字幕：ASS 输出 / 烧进画面
    want_ass = opts.ass or opts.burn
    if want_ass:
        from .subtitles import to_ass
        _emit_stage(on_event, "ass", "生成 ASS 字幕 …")
        to_ass(clean_blocks, outdir / "clean.ass", font=opts.ass_font,
               title=video.stem)
        files["clean.ass"] = outdir / "clean.ass"
        emit(on_event, "artifact", name="clean.ass")
    if opts.burn:
        ffmpeg = find_ffmpeg()
        if not ffmpeg:
            emit(on_event, "warn", message="没找到 ffmpeg，跳过 --burn")
        else:
            from .subtitles import burn_subtitles
            out = outdir / f"{video.stem}_subtitled.mp4"
            _emit_stage(on_event, "burn", "把字幕烧进画面（重编码，耗时较久）…")
            burn_subtitles(video, files["clean.ass"], out, ffmpeg)
            files[out.name] = out
            emit(on_event, "artifact", name=out.name)

    if opts.rewrite == "llm":
        _emit_stage(on_event, "llm", "LLM 通读润色 …")
        _save_text(outdir / "clean.llm.txt", llm_rewrite(clean_text, opts), on_event)
        files["clean.llm.txt"] = outdir / "clean.llm.txt"

    if opts.cut:
        ffmpeg = find_ffmpeg()
        if not ffmpeg:
            emit(on_event, "warn", message="没找到 ffmpeg，跳过 --cut")
        else:
            keeps = keep_intervals(segments, total)
            out = outdir / f"{video.stem}_tight.mp4"
            _emit_stage(on_event, "cut",
                        f"剪掉被删内容（保留 {len(keeps)} 段 / "
                        f"{sum(e - s for s, e in keeps):.1f}s of {total:.1f}s）…")
            cut_video(video, keeps, out, ffmpeg)
            files[out.name] = out
            emit(on_event, "artifact", name=out.name)

    res = Result(outdir=outdir, files=files, raw_text=raw_text, clean_text=clean_text,
                 counts=counts, removed=report,
                 language=str(getattr(info, "language", "")), duration=total,
                 speakers=speakers)
    emit(on_event, "done", result=res, percent=100.0)
    return res
