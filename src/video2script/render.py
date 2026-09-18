# -*- coding: utf-8 -*-
"""结果渲染：字幕块切割、SRT / Markdown 输出、按时序剪掉被删内容。"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .clean import Segment, speaker_prefix


def build_blocks(segments: list[Segment], max_chars: int = 42, max_dur: float = 6.0,
                 max_gap: float = 0.9, jt: str = ""):
    """把段内剩余词重新切成字幕块（按标点 / 长度 / 停顿）。

    开了说话人分离时，每段文本会带 ``说话人N：`` 前缀，字幕长度按前缀后的文本算。
    """
    blocks, cur, cstart = [], [], None
    for seg in segments:
        pre = speaker_prefix(seg)
        first_block_of_seg = True

        def flush(end):
            nonlocal cur, cstart
            if cur:
                blocks.append((cstart, end,
                               (pre if first_block_of_seg else "")
                               + jt.join(x.text for x in cur).strip()))
                cur, cstart = [], None

        for w in [w for w in seg.words if not w.drop]:
            if cur and (w.start - cur[-1].end > max_gap
                        or len(pre + jt.join(x.text for x in cur)) > max_chars
                        or w.end - cstart > max_dur):
                flush(cur[-1].end)
                first_block_of_seg = False
            if not cur:
                cstart = w.start
            cur.append(w)
            if re.search(r"[。！？!?…]$", w.text):
                flush(w.end)
                first_block_of_seg = False
        flush(cur[-1].end if cur else seg.end)
        first_block_of_seg = False
    return [b for b in blocks if b[2]]


def to_srt(blocks, path: Path) -> None:
    def ts(t: float) -> str:
        h = int(t // 3600)
        m = int((t % 3600) // 60)
        s = t % 60
        return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")

    with path.open("w", encoding="utf-8") as f:
        for i, (s, e, txt) in enumerate(blocks, 1):
            if e - s < 0.3:
                e = s + 0.6
            f.write(f"{i}\n{ts(s)} --> {ts(e)}\n{txt}\n\n")


def to_md(segments: list[Segment], path: Path, gap: float = 1.0, jt: str = "") -> None:
    """按停顿自动分段输出 Markdown；开了说话人分离时按说话人加小标题。"""
    join = (lambda xs: jt.join(xs)) if jt else (lambda xs: "".join(xs))
    groups: list[dict] = []
    pend = None
    for seg in segments:
        txt = join([w.text for w in seg.words if not w.drop]).strip()
        if not txt:
            continue
        new_group = (not groups or groups[-1]["speaker"] != seg.speaker
                     or (pend is not None and seg.start - pend > gap))
        if new_group:
            groups.append({"speaker": seg.speaker, "texts": []})
        groups[-1]["texts"].append(txt)
        pend = seg.end

    out: list[str] = []
    for g in groups:
        if g["speaker"]:
            out.append(f"**{g['speaker']}**")
        out.append(join(g["texts"]))
    path.write_text("\n\n".join(out) + "\n", encoding="utf-8")


def keep_intervals(segments: list[Segment], total: float, pad: float = 0.08):
    """剩余词覆盖的时间区间，用于 --cut 剪掉语气词。"""
    spans: list[list[float]] = []
    for seg in segments:
        for w in seg.words:
            if w.drop:
                continue
            s, e = max(0.0, w.start - pad), min(total, w.end + pad)
            if spans and s <= spans[-1][1] + 0.03:
                spans[-1][1] = max(spans[-1][1], e)
            else:
                spans.append([s, e])
    return [(s, e) for s, e in spans if e - s > 0.05]


def cut_video(video: Path, keeps: list[tuple], out: Path, ffmpeg: str) -> None:
    """按保留区间重编码，拼成更紧凑的视频（音画同步）。"""
    filt = []
    for i, (s, e) in enumerate(keeps):
        filt.append(f"[0:v]trim={s:.3f}:{e:.3f},setpts=PTS-STARTPTS[v{i}];"
                    f"[0:a]atrim={s:.3f}:{e:.3f},asetpts=PTS-STARTPTS[a{i}]")
    filt.append("".join(f"[v{i}][a{i}]" for i in range(len(keeps)))
                + f"concat=n={len(keeps)}:v=1:a=1[vo][ao]")
    subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                    "-i", str(video), "-filter_complex", ";".join(filt),
                    "-map", "[vo]", "-map", "[ao]",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                    "-c:a", "aac", str(out)], check=True)
