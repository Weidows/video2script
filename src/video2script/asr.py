# -*- coding: utf-8 -*-
"""ASR 层：faster-whisper 逐字转写（词级时间戳）。

不需要 GPU，也不需要在系统里装 ffmpeg —— 解码走 PyAV 自带的 FFmpeg 库。
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from .clean import Segment, Word
from .config import DEFAULT_MODEL_DIR, use_hf_mirror


def transcribe(video: str | Path, model_name: str = "small", lang: str | None = "zh",
               device: str = "cpu", compute_type: str = "int8",
               model_dir: str | Path | None = None, prompt: str | None = None,
               use_vad: bool = True, beam_size: int = 5,
               on_progress: Callable[[float, float, str], None] | None = None):
    """返回 (segments, info)。``on_progress(done_s, total_s, text)`` 用于画进度条。"""
    use_hf_mirror()  # 必须在导入 faster_whisper 之前
    from faster_whisper import WhisperModel

    model = WhisperModel(model_name, device=device, compute_type=compute_type,
                         download_root=str(model_dir or DEFAULT_MODEL_DIR))
    segs, info = model.transcribe(
        str(video),
        language=lang,
        beam_size=beam_size,
        vad_filter=use_vad,
        vad_parameters=dict(min_silence_duration_ms=300),
        word_timestamps=True,
        condition_on_previous_text=False,   # 抑制长音频复读/幻觉
        initial_prompt=prompt,
    )
    total = float(getattr(info, "duration", 0.0) or 0.0)
    out: list[Segment] = []
    for s in segs:
        words = [Word(w.word.strip(), w.start, w.end, getattr(w, "probability", 1.0))
                 for w in (s.words or []) if w.word and w.word.strip()]
        out.append(Segment(s.start, s.end, s.text.strip(), words))
        if on_progress:
            on_progress(min(s.end, total) if total else s.end, total, s.text.strip())
    return out, info
