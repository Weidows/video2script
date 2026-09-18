# -*- coding: utf-8 -*-
"""字幕：ASS 生成 + 烧录进视频（可选功能，仅 --ass / --burn 时用到）。"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{size},&H00FFFFFF,&H000000FF,&H00101010,&H80000000,{bold},0,0,0,100,100,0,0,1,{outline},1,2,{ml},{mr},{mv},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

# Windows 上这些字体基本都有；macOS/Linux 会自动回落到系统字体
DEFAULT_FONT = "Microsoft YaHei"


def ass_time(t: float) -> str:
    """ASS 用 H:MM:SS.cc（百分秒）。"""
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h:d}:{m:02d}:{s:05.2f}"


def escape(text: str) -> str:
    """ASS 文本转义：花括号是特效标记，换行要用 \\N。"""
    t = text.replace("\\", "\\\\").replace("{", "（").replace("}", "）")
    t = re.sub(r"[\r\n]+", r"\\N", t).strip()
    return t


def to_ass(blocks, path: Path, font: str = DEFAULT_FONT, size: int = 64,
           outline: int = 3, margin_v: int = 48, title: str = "video2script") -> None:
    """blocks: [(start, end, text), ...]"""
    body = [ASS_HEADER.format(font=font, size=size, outline=outline,
                              bold=-1, ml=60, mr=60, mv=margin_v),
            f"; {title}\n"]
    for s, e, txt in blocks:
        if e - s < 0.3:
            e = s + 0.6
        body.append(f"Dialogue: 0,{ass_time(s)},{ass_time(e)},Default,,0,0,0,,"
                    f"{escape(txt)}\n")
    path.write_text("".join(body), encoding="utf-8")


def burn_subtitles(video: Path, ass: Path, out: Path, ffmpeg: str) -> None:
    """把 ASS 烧进画面（音轨直接 copy，不重编码）。"""
    # 用相对路径 + cwd 规避 Windows 下 filter 里盘符/反斜杠的转义坑
    subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                    "-i", str(video.resolve()),
                    "-vf", f"subtitles={ass.name}",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                    "-c:a", "copy", str(out.resolve())],
                   cwd=str(ass.parent), check=True)
