# -*- coding: utf-8 -*-
"""顺滑规则层回归测试：不加载任何模型，秒级跑完。"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from video2script.clean import Segment, Word, norm, smooth  # noqa: E402


def mk(spec):
    """spec: [(词, 起始, 结束), ...] 全部落在同一个 segment 里。"""
    ws = [Word(t, s, e) for t, s, e in spec]
    return [Segment(spec[0][1], spec[-1][2], "".join(t for t, _, _ in spec), ws)]


def run(spec, level=2, lang="zh"):
    segs = mk(spec)
    smooth(segs, level, lang)
    jt = " " if lang == "en" else ""
    return jt.join(s.text for s in segs)


def test_norm_keeps_word_spacing():
    assert norm("You know,") == "you know"
    assert norm("把，") == "把"
    assert norm(" Um. ") == "um"


ZH = [("呃、", 0.0, 0.4), ("那个，", 0.9, 1.3), ("我", 1.5, 1.7),
      ("今天", 1.7, 2.0), ("想", 2.0, 2.2), ("讲", 2.2, 2.4), ("一下", 2.4, 2.7),
      ("这个，", 2.8, 3.1), ("嗯，", 3.3, 3.6), ("这个", 3.8, 4.0), ("项目", 4.0, 4.4),
      ("的", 4.4, 4.5), ("一个，", 4.6, 4.9), ("一个，", 5.0, 5.3), ("就是", 5.4, 5.7),
      ("进度", 5.8, 6.1), ("问题。", 6.1, 6.6)]


def test_zh_level2_keeps_pause_unguarded_discourse():
    """level 2 只删"被停顿包住"的口头禅，这里'就是'前后没有足够停顿 → 保留。"""
    assert run(ZH, 2) == "我今天想讲一下这个项目的一个就是进度问题。"


def test_zh_level3_drops_all_discourse():
    assert run(ZH, 3) == "我今天想讲一下项目的一个进度问题。"


def test_zh_level1_keeps_discourse():
    """level 1 只删语气词和重复，'那个' 这类口头禅保留（含它后面的逗号）。"""
    assert run(ZH, 1) == "那个，我今天想讲一下这个项目的一个就是进度问题。"


def test_zh_cross_token_stutter():
    assert run([("下周", 0.0, 0.4), ("我，", 0.6, 0.8), ("我，", 1.0, 1.2),
                ("我觉得", 1.4, 1.9), ("可以", 1.9, 2.2), ("开始", 2.2, 2.5),
                ("测试。", 2.5, 3.0)]) == "下周我觉得可以开始测试。"


def test_zh_reduplication_whitelist_is_kept():
    assert run([("我", 0.0, 0.2), ("想", 0.2, 0.4), ("谢谢", 0.4, 0.8),
                ("妈妈", 0.8, 1.2), ("刚刚", 1.2, 1.5), ("看看", 1.5, 1.9)]) \
        == "我想谢谢妈妈刚刚看看"


def test_zh_in_word_and_adjacent_repeats():
    assert run([("把，", 0.0, 0.4), ("把", 0.6, 0.8), ("语音识别", 0.8, 1.4),
                ("的", 1.4, 1.5), ("模块", 1.5, 1.9), ("做完了。", 1.9, 2.4)]) \
        == "把语音识别的模块做完了。"


def test_zh_phrase_level_repeat():
    assert run([("把", 0.0, 0.2), ("语音识别", 0.2, 0.8), ("的", 0.8, 0.9),
                ("模块", 0.9, 1.3), ("把", 1.6, 1.8), ("语音识别", 1.8, 2.4),
                ("的", 2.4, 2.5), ("模块", 2.5, 2.9), ("做完了。", 2.9, 3.4)]) \
        == "把语音识别的模块做完了。"


def test_en_fillers_two_word_markers_and_spacing():
    assert run([("Um,", 0.0, 0.3), ("so,", 0.5, 0.8), ("uh,", 1.0, 1.3),
                ("I", 1.5, 1.6), ("wanted", 1.6, 2.0), ("to,", 2.0, 2.2),
                ("to,", 2.3, 2.5), ("talk", 2.6, 2.9), ("about", 2.9, 3.2),
                ("the,", 3.3, 3.5), ("the", 3.6, 3.8), ("project", 3.8, 4.2),
                ("status.", 4.2, 4.7), ("You", 5.2, 5.4), ("know,", 5.4, 5.7),
                ("uh,", 5.9, 6.1), ("it's,", 6.3, 6.5), ("it's", 6.6, 6.8),
                ("fine.", 6.8, 7.1)], 2, "en") \
        == "so, I wanted to talk about the project status. it's fine."


def test_report_counts_match_drops():
    segs = mk(ZH)
    rep = smooth(segs, 2, "zh")
    dropped = sum(1 for s in segs for w in s.words if w.drop)
    assert sum(len(v) for v in rep.values()) == dropped
    assert rep["filler"] and rep["repeat"] and rep["discourse"]


def test_no_drop_flag_left_over_on_rerun():
    """同一个 Segment 反复跑不能累积脏状态。"""
    segs = mk(ZH)
    once = smooth(segs, 2, "zh")
    again = smooth(segs, 2, "zh")
    assert {k: len(v) for k, v in once.items()} == {k: len(v) for k, v in again.items()}


@pytest.mark.parametrize("level", [1, 2, 3])
def test_empty_input_is_safe(level):
    segs = [Segment(0.0, 0.0, "", [])]
    assert sum(len(v) for v in smooth(segs, level, "zh").values()) == 0
