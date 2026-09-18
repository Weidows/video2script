"""video2script —— 视频 → 文稿（自动剔除语气词/结巴/重复词）。

公开 API：
    from video2script import Options, run
    run("会议.mp4", Options(lang="zh", model="medium"))

命令行：``video2script``；图形界面：``video2script-gui``。
"""
from .clean import Segment, Word, norm, smooth
from .config import DEFAULT_MODEL_DIR, find_ffmpeg, use_hf_mirror
from .pipeline import Options, run

__version__ = "0.4.0"
__all__ = ["Options", "run", "Segment", "Word", "norm", "smooth",
           "find_ffmpeg", "use_hf_mirror", "DEFAULT_MODEL_DIR", "__version__"]
