# -*- coding: utf-8 -*-
"""说话人分离（可选功能，需要 sherpa-onnx：pip install "video2script[diar]"）。

用 pyannote-segmentation-3.0 做分段 + 3D-Speaker CAM++ 做声纹嵌入 + 快速聚类，
模型只有 ~35 MB，纯 CPU、onnxruntime 推理，不需要 torch / 不需要上传音频。
"""
from __future__ import annotations

import os
import tarfile
import urllib.request
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

SEG_URL = ("https://github.com/k2-fsa/sherpa-onnx/releases/download/"
           "speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2")
EMB_URL = ("https://github.com/k2-fsa/sherpa-onnx/releases/download/"
           "speaker-recongition-models/"
           "3dspeaker_speech_campplus_sv_zh-cn_16k-common.onnx")
SEG_NAME = "sherpa-onnx-pyannote-segmentation-3-0.onnx"
EMB_NAME = "3dspeaker_speech_campplus_sv_zh-cn_16k-common.onnx"


@dataclass
class Turn:
    start: float
    end: float
    speaker: str


def _download(url: str, dest: Path, on_progress: Callable | None = None) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url, timeout=120) as r, tmp.open("wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        got = 0
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            got += len(chunk)
            if on_progress:
                on_progress(got, total, dest.name)
    os.replace(tmp, dest)


def ensure_models(model_dir: Path, on_event: Callable | None = None):
    """确保分段/声纹模型就位，返回 (seg_onnx, emb_onnx)。"""
    model_dir.mkdir(parents=True, exist_ok=True)
    seg = model_dir / SEG_NAME
    emb = model_dir / EMB_NAME
    cb = (lambda got, total, name: on_event(
        "progress", {"stage": "diar", "done": got, "total": total or 1,
                     "text": f"下载 {name}"})) if on_event else None

    def note(msg: str) -> None:
        if on_event:
            on_event("stage", {"stage": "diar", "message": msg})

    if not seg.exists():
        note("下载说话人分段模型 (~6 MB，只下一次) …")
        tar = model_dir / "seg.tar.bz2"
        _download(os.environ.get("V2S_SEG_URL", SEG_URL), tar, cb)
        with tarfile.open(tar) as tf:
            for m in tf.getmembers():
                if m.name.endswith(".onnx"):
                    tf.extract(m, model_dir, filter="data")
                    (model_dir / m.name).replace(seg)
        tar.unlink(missing_ok=True)
    if not emb.exists():
        note("下载声纹模型 (~28 MB，只下一次) …")
        _download(os.environ.get("V2S_EMB_URL", EMB_URL), emb, cb)
    return seg, emb


def extract_wav(src: Path, dst: Path, sample_rate: int = 16000) -> Path:
    """用 PyAV（自带 FFmpeg）把任意音视频转成 16k 单声道 wav，不需要系统 ffmpeg。"""
    import av

    with av.open(str(src)) as container:
        stream = next((s for s in container.streams if s.type == "audio"), None)
        if stream is None:
            raise ValueError(f"{src} 里没有音频轨")
        resampler = av.AudioResampler(format="s16", layout="mono", rate=sample_rate)
        with wave.open(str(dst), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sample_rate)
            for frame in container.decode(stream):
                for res in resampler.resample(frame):
                    w.writeframes(bytes(res.planes[0]))
            for res in resampler.resample(None):   # flush
                w.writeframes(bytes(res.planes[0]))
    return dst


def diarize(video: Path, model_dir: Path, num_speakers: int = -1,
            threshold: float = 0.5, workdir: Path | None = None,
            on_event: Callable | None = None) -> list[Turn]:
    """返回 [{start, end, speaker}]，speaker 形如 说话人1（按首次出现顺序编号）。"""
    try:
        import numpy as np
        import sherpa_onnx
    except ImportError as e:  # 可选依赖
        raise RuntimeError('需要先安装可选依赖：pip install "video2script[diar]"') from e

    import tempfile

    seg_model, emb_model = ensure_models(model_dir, on_event)
    tmpdir = Path(tempfile.mkdtemp(prefix="v2s_diar_"))
    try:
        wav = extract_wav(video, tmpdir / "diar_16k.wav")
        with wave.open(str(wav)) as w:
            raw = w.readframes(w.getnframes())
    finally:
        for f in tmpdir.glob("*"):
            f.unlink(missing_ok=True)
        tmpdir.rmdir()
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

    config = sherpa_onnx.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(
                model=str(seg_model)),
            num_threads=1, debug=False, provider="cpu"),
        embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(
            model=str(emb_model), num_threads=1, debug=False, provider="cpu"),
        clustering=sherpa_onnx.FastClusteringConfig(
            num_clusters=num_speakers, threshold=threshold),
        min_duration_on=0.3, min_duration_off=0.5)
    sd = sherpa_onnx.OfflineSpeakerDiarization(config)
    if sd.sample_rate != 16000:
        raise RuntimeError(f"模型要求 {sd.sample_rate} Hz 采样率")
    result = sd.process(samples)
    turns: list[Turn] = []
    for r in result.sort_by_start_time():
        turns.append(Turn(float(r.start), float(r.end), f"spk{int(r.speaker) + 1}"))
    # 按"谁先说"重新编号，让第一段永远是 说话人1
    order: dict[str, str] = {}
    for t in turns:
        if t.speaker not in order:
            order[t.speaker] = f"说话人{len(order) + 1}"
    for t in turns:
        t.speaker = order[t.speaker]
    if on_event:
        on_event("stage", {"stage": "diar",
                           "message": f"分出 {len(order)} 个说话人 / {len(turns)} 段"})
    return turns


def assign_speakers(segments, turns: list[Turn], prefix: bool = True) -> dict:
    """按时间重叠把说话人贴到每个转写段上（重叠最多者胜，没重叠就取最近）。"""
    counts: dict[str, int] = {}
    for seg in segments:
        best, best_ov = "", 0.0
        for t in turns:
            ov = max(0.0, min(seg.end, t.end) - max(seg.start, t.start))
            if ov > best_ov:
                best, best_ov = t.speaker, ov
        if not best and turns:
            mid = (seg.start + seg.end) / 2
            best = min(turns, key=lambda t: abs((t.start + t.end) / 2 - mid)).speaker
        seg.speaker = best if prefix else ""
        counts[best] = counts.get(best, 0) + 1
    return counts
