# -*- coding: utf-8 -*-
"""渲染层测试：字幕分块 / SRT 时间戳 / 保留区间（纯函数，无需模型）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from video2script.clean import Segment, Word  # noqa: E402
from video2script.render import build_blocks, keep_intervals, to_md, to_srt  # noqa: E402


def seg(spec, dropped=()):
    ws = [Word(t, s, e, drop=("x" if t in dropped else "")) for t, s, e in spec]
    return Segment(spec[0][1], spec[-1][2], "".join(t for t, _, _ in spec), ws)


def test_srt_timestamps_keep_milliseconds(tmp_path):
    s = seg([("你好", 1.5, 2.25), ("世界。", 2.25, 3.0)])
    p = tmp_path / "a.srt"
    to_srt(build_blocks([s]), p)
    body = p.read_text(encoding="utf-8")
    assert "00:00:01,500 --> 00:00:03,000" in body


def test_srt_never_zero_length(tmp_path):
    s = seg([("嗯", 1.0, 1.0), ("好。", 1.0, 1.0)])
    p = tmp_path / "b.srt"
    to_srt(build_blocks([s]), p)
    for line in p.read_text(encoding="utf-8").splitlines():
        if "-->" in line:
            a, b = [x.strip() for x in line.split("-->")]
            assert a != b


def test_blocks_evidence_split_on_gap():
    s = seg([("前半句。", 0.0, 1.0), ("后半句。", 3.0, 4.0)])
    blocks = build_blocks([s], max_gap=0.9)
    assert len(blocks) == 2


def test_keep_intervals_merges_and_pads():
    s = seg([("甲", 0.0, 1.0), ("乙", 1.05, 2.0), ("丙", 5.0, 6.0)])
    keeps = keep_intervals([s], total=10.0, pad=0.05)
    assert len(keeps) == 2
    assert keeps[0][0] == 0.0 and keeps[0][1] > 2.0
    assert keeps[1][0] < 5.0


def test_keep_intervals_skips_dropped_words():
    s = seg([("呃", 0.0, 0.5), ("正文", 1.0, 2.0)], dropped={"呃"})
    keeps = keep_intervals([s], total=5.0, pad=0.0)
    assert len(keeps) == 1
    assert keeps[0] == (1.0, 2.0)


def test_md_groups_paragraphs_by_pause(tmp_path):
    a = seg([("第一段。", 0.0, 1.0)])
    b = seg([("第二段。", 5.0, 6.0)])
    p = tmp_path / "c.md"
    to_md([a, b], p, gap=1.0)
    assert p.read_text(encoding="utf-8").count("\n\n") == 1


def test_md_joins_english_with_spaces(tmp_path):
    s = seg([("hello", 0.0, 0.5), ("world.", 0.5, 1.0)])
    p = tmp_path / "d.md"
    to_md([s], p, jt=" ")
    assert p.read_text(encoding="utf-8").strip() == "hello world."
