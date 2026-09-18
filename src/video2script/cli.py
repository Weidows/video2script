# -*- coding: utf-8 -*-
"""命令行入口：``video2script`` 或 ``python -m video2script.cli``"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import find_ffmpeg
from .pipeline import LEVELS, MODELS, Options, run


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="video2script",
        description="视频 → 文稿（自动剔除语气词 / 结巴 / 重复词）",
        epilog="示例： video2script 会议.mp4 --model medium --level 2 --cut")
    p.add_argument("video", type=Path, help="输入视频/音频文件")
    p.add_argument("-o", "--outdir", type=Path, default=None,
                   help="输出目录（默认 <视频名>_transcript/）")
    p.add_argument("--lang", default="zh", choices=("zh", "en", "auto"),
                   help="语言，默认 zh")
    p.add_argument("--model", default="small", choices=MODELS,
                   help="Whisper 规模（中文建议 medium 以上），默认 small")
    p.add_argument("--device", default="cpu", choices=("cpu", "cuda"))
    p.add_argument("--compute-type", default="int8",
                   choices=("int8", "int8_float16", "float16", "float32"))
    p.add_argument("--level", type=int, default=2, choices=LEVELS,
                   help="顺滑力度：1 只删语气词+重复字；2 再删停顿包住的口头禅；3 全删口头禅")
    p.add_argument("--no-vad", action="store_true", help="关闭静音切分")
    p.add_argument("--rewrite", choices=("none", "llm"), default="none",
                   help="再让 LLM 通读润色一遍（需要 API key）")
    p.add_argument("--llm-base", default=None, help="OpenAI 兼容地址，或 V2S_LLM_BASE")
    p.add_argument("--llm-key", default=None, help="API key，或 V2S_LLM_KEY")
    p.add_argument("--llm-model", default=None, help="模型名，或 V2S_LLM_MODEL")
    p.add_argument("--prompt", default=None, help="自定义转写提示词")
    p.add_argument("--cut", action="store_true",
                   help="额外输出剪掉语气词的 *_tight.mp4（需 ffmpeg）")
    p.add_argument("-q", "--quiet", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cut and not find_ffmpeg() and not args.quiet:
        print("! 没找到 ffmpeg，--cut 会被跳过（装一个或把 ffmpeg 加到 PATH）",
              file=sys.stderr)

    opts = Options(lang=args.lang, model=args.model, device=args.device,
                   compute_type=args.compute_type, level=args.level,
                   vad=not args.no_vad, cut=args.cut, rewrite=args.rewrite,
                   prompt=args.prompt, outdir=args.outdir, llm_base=args.llm_base,
                   llm_key=args.llm_key, llm_model=args.llm_model)

    def on_event(kind: str, data: dict) -> None:
        if args.quiet:
            return
        if kind == "stage":
            print(f"[{data['stage']}] {data['message']}", flush=True)
        elif kind == "warn":
            print(f"! {data['message']}", file=sys.stderr, flush=True)
        elif kind == "progress":
            total = data.get("total") or 0
            pct = f"{data['done'] / total * 100:5.1f}%" if total else "  ... "
            print(f"\r      {pct} {data['text'][:48]:<48}", end="", flush=True)

    try:
        res = run(args.video, opts, on_event=on_event)
    except FileNotFoundError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\n已中断", file=sys.stderr)
        return 130

    if not args.quiet:
        c = res.counts
        print(f"\n完成。语气词 {c['filler']}、重复 {c['repeat']}、"
              f"短语重复 {c['phrase_repeat']}、口头禅 {c['discourse']}、"
              f"半截词 {c['partial']}  ← 共删除 {sum(c.values())} 处，"
              f"落在 {res.duration:.0f}s 音频上")
        print(f"输出目录：{res.outdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
