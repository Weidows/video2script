# -*- coding: utf-8 -*-
"""结果渲染：字幕块切割、SRT / Markdown 输出、按时序剪掉被删内容。"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .clean import Segment


def build_blocks(segments: list[Segment], max_chars: int = 42, max_dur: float = 6.0,
                 max_gap: float = 0.9, jt: str = ""):
    """把段内剩余词重新切成字幕块（按标点 / 长度 / 停顿）。"""
    blocks, cur, cstart = [], [], None
    for seg in segments:
        for w in [w for w in seg.words if not w.drop]:
            if cur and (w.start - cur[-1].end > max_gap
                        or len(jt.join(x.text for x in cur)) > max_chars
                        or w.end - cstart > max_dur):
                blocks.append((cstart, cur[-1].end,
                               jt.join(x.text for x in cur).strip()))
                cur, cstart = [], None
            if not cur:
                cstart = w.start
            cur.append(w)
            if re.search(r"[。！？!?…]$", w.text):
                blocks.append((cstart, w.end, jt.join(x.text for x in cur).strip()))
                cur, cstart = [], None
        if cur:
            blocks.append((cstart, cur[-1].end, jt.join(x.text for x in cur).strip()))
            cur, cstart = [], None
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
    """按停顿自动分段输出 Markdown。"""
    paras, cur, pend = [], [], None
    for seg in segments:
        txt = jt.join(w.text for w in seg.words if not w.drop).strip()
        if not txt:
            continue
        if pend is not None and seg.start - pend > gap:
            paras.append(jt.join(cur) if jt else "".join(cur))
            cur = []
        cur.append(txt)
        pend = seg.end
    if cur:
        paras.append(jt.join(cur) if jt else "".join(cur))
    path.write_text("\n\n".join(paras) + "\n", encoding="utf-8")


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
