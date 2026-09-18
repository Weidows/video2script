# -*- coding: utf-8 -*-
"""路径、环境变量、外部工具探测。"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

# 模型缓存：默认 ~/.cache/video2script/models，可用 V2S_MODEL_DIR 覆盖
DEFAULT_MODEL_DIR = Path(os.environ.get("V2S_MODEL_DIR")
                         or Path.home() / ".cache" / "video2script" / "models")

FFMPEG_CANDIDATES = (
    Path.home() / "scoop/apps/ffmpeg-shared/current/bin/ffmpeg.exe",
    Path("C:/ffmpeg/bin/ffmpeg.exe"),
    Path("/opt/homebrew/bin/ffmpeg"),
    Path("/usr/local/bin/ffmpeg"),
    Path("/usr/bin/ffmpeg"),
)


def use_hf_mirror() -> str:
    """huggingface.co 在部分网络下不可达；未显式设置时回落到 hf-mirror。

    注意：必须在导入 faster_whisper / huggingface_hub 之前调用。
    """
    if not os.environ.get("HF_ENDPOINT"):
        os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
    return os.environ["HF_ENDPOINT"]


def find_ffmpeg() -> str | None:
    """找 ffmpeg（仅 --cut 需要；转写本身靠 PyAV 内置解码，不需要它）。"""
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    for p in FFMPEG_CANDIDATES:
        if p.exists():
            return str(p)
    return None


def default_prompt(lang: str | None) -> str:
    """默认用"逐字倾向"的提示词，让 Whisper 别偷偷把语气词吞掉。"""
    if lang == "zh":
        return ("以下是普通话口语录音，请逐字转写，保留说话人的语气词、口吃和重复，"
                "不要自动修正或省略。语气词请写成：嗯、呃、啊、哦、哎、那个、就是。")
    if lang == "en":
        return ("Verbatim transcription. Keep filler words, stutters and repetitions "
                "exactly as spoken; do not clean up. Fillers should be written as: "
                "um, uh, erm, hmm, you know, I mean.")
    return ("Verbatim transcription: keep filler words, stutters and repetitions as "
            "spoken, do not clean up.")


def open_folder(path: Path) -> None:
    """在文件管理器里打开目录（GUI 用）。"""
    if sys.platform == "win32":
        os.startfile(str(path))  # noqa: S606  (Windows only)
    elif sys.platform == "darwin":
        import subprocess
        subprocess.Popen(["open", str(path)])
    else:
        import subprocess
        subprocess.Popen(["xdg-open", str(path)])
