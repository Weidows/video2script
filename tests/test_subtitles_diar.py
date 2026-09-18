# -*- coding: utf-8 -*-
"""字幕与说话人相关测试（纯函数，不需要模型）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from video2script.clean import Segment, Word  # noqa: E402
from video2script.diarize import Turn, assign_speakers  # noqa: E402
from video2script.render import build_blocks, to_md  # noqa: E402
from video2script.subtitles import ass_time, escape, to_ass  # noqa: E402


def seg(spec, speaker=""):
    ws = [Word(t, s, e) for t, s, e in spec]
    return Segment(spec[0][1], spec[-1][2], "", ws, speaker=speaker)


# ---------------- ASS
def test_ass_time_format():
    assert ass_time(0) == "0:00:00.00"
    assert ass_time(3661.234) == "1:01:01.23"


def test_ass_escape_braces_and_newlines():
    assert escape("a{b}c") == "a（b）c"
    assert escape("第一行\n第二行") == "第一行\\N第二行"


def test_ass_header_and_dialogue(tmp_path):
    p = tmp_path / "s.ass"
    to_ass([(1.0, 2.5, "你好"), (2.5, 6.0, "世界")], p, font="F", size=40)
    body = p.read_text(encoding="utf-8")
    assert "[V4+ Styles]" in body and "Style: Default,F,40" in body
    assert "Dialogue: 0,0:00:01.00,0:00:02.50,Default,,0,0,0,,你好" in body


def test_ass_zero_length_becomes_visible(tmp_path):
    p = tmp_path / "z.ass"
    to_ass([(1.0, 1.0, "嗯")], p)
    line = [l for l in p.read_text(encoding="utf-8").splitlines()
            if l.startswith("Dialogue")][0]
    a, b = line.split(",")[1:3]
    assert a != b


# ---------------- 说话人
def test_assign_speakers_by_overlap():
    segs = [seg([("甲说话", 0.0, 2.0)]), seg([("乙说话", 3.0, 5.0)]),
            seg([("还是甲", 6.0, 8.0)])]
    turns = [Turn(0.0, 2.5, "说话人1"), Turn(2.6, 5.5, "说话人2"),
             Turn(5.6, 9.0, "说话人1")]
    counts = assign_speakers(segs, turns)
    assert [s.speaker for s in segs] == ["说话人1", "说话人2", "说话人1"]
    assert counts == {"说话人1": 2, "说话人2": 1}


def test_assign_speakers_nearest_when_no_overlap():
    segs = [seg([("间隙里的话", 10.0, 11.0)])]
    turns = [Turn(0.0, 5.0, "说话人1"), Turn(11.2, 14.0, "说话人2")]
    assign_speakers(segs, turns)
    assert segs[0].speaker == "说话人2"


def test_speaker_prefix_in_blocks_and_md(tmp_path):
    s = seg([("你好。", 0.0, 1.0), ("再见。", 1.0, 2.0)], speaker="说话人1")
    blocks = build_blocks([s])
    assert len(blocks) == 2
    assert blocks[0][2].startswith("说话人1：")
    assert not blocks[1][2].startswith("说话人1：")   # 前缀只在每段第一块出现
    p = tmp_path / "m.md"
    to_md([s], p)
    text = p.read_text(encoding="utf-8")
    assert "**说话人1**" in text and "你好。再见。" in text


def test_no_speaker_no_prefix(tmp_path):
    s = seg([("你好。", 0.0, 1.0)])
    p = tmp_path / "n.md"
    to_md([s], p)
    assert "：" not in p.read_text(encoding="utf-8")
