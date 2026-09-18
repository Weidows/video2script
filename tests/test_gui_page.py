# -*- coding: utf-8 -*-
"""GUI 页面 / 进度 / 日志的回归测试（不依赖浏览器，纯服务端与纯函数）。"""
import re
from pathlib import Path

import pytest

from video2script import gui, pipeline
from video2script.config import ASSETS_DIR

ROOT = Path(__file__).resolve().parent.parent


def make_job(tmp_path, name="a.mp4"):
    v = tmp_path / name
    v.write_bytes(b"x")
    return gui.Job("j1", v, tmp_path / "out")


# --------------------------------------------------------------- 页面资源
def test_page_template_is_a_real_file():
    f = ASSETS_DIR / "gui.html"
    assert f.exists() and f.stat().st_size > 3000


def test_render_page_injects_version():
    html = gui.render_page().decode("utf-8")
    assert "{{VERSION}}" not in html
    from video2script import __version__
    assert __version__ in html


@pytest.mark.parametrize("needle", [
    'id="preview"',            # 选中文件后的预览卡片
    'id="pvbox"',              # 预览容器（video/audio）
    'id="live"',               # 实时逐字稿
    'id="log"',                # 完整日志面板
    'id="reveal"',             # 打开输出目录
    'id="copypath"',           # 复制输出路径（打不开时的兜底）
    'id="arts"',               # 产物边跑边出现
    'class="bar"',             # 进度条
    '/api/media?id=',          # 预览播放源
])
def test_page_has_ui_hooks(needle):
    assert needle in gui.PAGE


def test_page_has_no_truncating_log_slice():
    # 老版本只显示最后 8 行：s.log.slice(-8)
    assert "slice(-8)" not in gui.PAGE


# --------------------------------------------------------------- Range
@pytest.mark.parametrize("header,size,want", [
    ("bytes=0-99", 1000, (0, 99)),
    ("bytes=100-", 1000, (100, 999)),
    ("bytes=-100", 1000, (900, 999)),
    ("bytes=0-99999", 1000, (0, 999)),      # 超出末尾要截断
    ("bytes=9999-", 1000, None),            # 起点越界
    ("bytes=-", 1000, None),
    ("items=0-9", 1000, None),
    (None, 1000, None),
    ("bytes=0-99", 0, None),
])
def test_parse_range(header, size, want):
    assert gui.parse_range(header, size) == want


# --------------------------------------------------------------- 进度
def test_stage_percent_is_monotonic():
    names = ["start", "asr", "clean", "diar", "render", "ass", "llm", "burn", "cut", "done"]
    vals = [pipeline.stage_pct(n) for n in names]
    assert vals == sorted(vals)
    assert vals[-1] == 100.0
    assert vals[0] > 0.0                     # 一开始就不能停在 0%


def test_every_emitted_stage_has_a_percent():
    """回归：pipeline 里每个 _emit_stage 的阶段名都要在 PCT 表里，否则进度会倒回 0%。"""
    src = (ROOT / "src" / "video2script" / "pipeline.py").read_text(encoding="utf-8")
    used = set(re.findall(r'_emit_stage\(on_event,\s*"([a-z]+)"', src))
    assert used, "没找到任何 _emit_stage 调用"
    missing = {n for n in used if n not in pipeline.PCT}
    assert not missing, f"这些阶段没有百分比预算：{sorted(missing)}"


def test_asr_progress_maps_into_its_budget(tmp_path, monkeypatch):
    """ASR 进度应落在 start..asr 之间，并按 done/total 线性推进。"""
    seen = []
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"x")
    opts = pipeline.Options(model="tiny")

    def fake_transcribe(video, on_progress=None, **kw):
        on_progress(1, 4, "第一段")
        on_progress(4, 4, "第四段")
        raise RuntimeError("stop here")

    monkeypatch.setattr(pipeline, "transcribe", fake_transcribe)
    with pytest.raises(RuntimeError):
        pipeline.run(video, opts, on_event=lambda k, d: seen.append((k, d)))
    pcts = [d["percent"] for k, d in seen if k == "progress"]
    assert pcts == [pipeline.stage_pct("start")
                    + (pipeline.stage_pct("asr") - pipeline.stage_pct("start")) * 0.25,
                    pipeline.stage_pct("asr")]


# --------------------------------------------------------------- 事件 → 任务状态
def test_on_event_keeps_partial_text_and_artifacts(tmp_path):
    job = make_job(tmp_path)
    gui._on_event(job, "stage", {"stage": "asr", "message": "加载模型", "percent": 1.0})
    gui._on_event(job, "progress", {"percent": 30.0, "text": "今天讲项目进度"})
    gui._on_event(job, "progress", {"percent": 40.0, "text": "今天讲项目进度"})  # 重复段不重复记
    gui._on_event(job, "artifact", {"name": "raw.txt"})
    gui._on_event(job, "artifact", {"name": "raw.txt"})                        # 去重
    assert job.percent == 40.0
    assert job.partial == ["今天讲项目进度"]
    assert job.artifacts == ["raw.txt"]
    assert job.stage == "加载模型"


def test_log_is_not_flooded_by_progress(tmp_path):
    """回归：老版本每个进度事件都写一行日志，导致日志被刷爆、只剩最新几条。"""
    job = make_job(tmp_path)
    for i in range(600):
        gui._on_event(job, "progress", {"percent": i / 6, "text": f"第{i}段"})
    assert len(job.partial) == 600          # 逐字稿一条不少
    assert len(job.log) <= 15               # 日志只按 10% 记一条


def test_log_keeps_old_lines(tmp_path):
    """回归：日志不能被截断成只剩最后几条。"""
    job = make_job(tmp_path)
    for i in range(500):
        job.add(f"line {i}")
    assert job.log[0] == "line 0" and job.log[-1] == "line 499"


def test_snapshot_shape(tmp_path):
    job = make_job(tmp_path)
    snap = job.snapshot()
    for k in ("state", "stage", "percent", "log", "partial", "artifacts", "outdir"):
        assert k in snap


# --------------------------------------------------------------- 产物事件
def test_pipeline_emits_artifacts_in_write_order(tmp_path, monkeypatch):
    """产物要边写边报（GUI 才能边跑边下载），名字与磁盘上的文件一一对应。"""
    from types import SimpleNamespace

    from video2script import clean

    video = tmp_path / "c.mp4"
    video.write_bytes(b"x")
    segs = [clean.Segment(start=0.0, end=1.0, text="呃，你好。",
                          words=[clean.Word("呃", 0.0, 0.3), clean.Word("你好", 0.3, 1.0)]),
            clean.Segment(start=1.0, end=2.0, text="嗯，再见。",
                          words=[clean.Word("嗯", 1.0, 1.2), clean.Word("再见", 1.2, 2.0)])]
    info = SimpleNamespace(language="zh", language_probability=0.99, duration=2.0)
    monkeypatch.setattr(pipeline, "transcribe", lambda *a, **k: (segs, info))

    events: list[tuple[str, dict]] = []
    outdir = tmp_path / "out"
    pipeline.run(video, pipeline.Options(model="tiny", outdir=outdir),
                 on_event=lambda k, d: events.append((k, d)))

    names = [d["name"] for k, d in events if k == "artifact"]
    assert names[:2] == ["raw.txt", "raw.srt"]        # ASR 一结束就能给
    for n in ("clean.txt", "clean.srt", "clean.md", "report.json"):
        assert n in names
    assert all((outdir / n).exists() for n in names)
    stages = [d["stage"] for k, d in events if k == "stage"]
    assert stages[0] == "start" and "clean" in stages
    assert events[-1][0] == "done" and events[-1][1]["percent"] == 100.0



def test_dev_group_matches_dev_extra():
    """[dependency-groups].dev 与 [project.optional-dependencies].dev 不能漂移。"""
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    extra = re.findall(r"^dev = \[(.*?)\]", text, re.M)
    assert len(extra) == 2, f"应当有两处 dev 声明，实际 {len(extra)} 处"
    norm = lambda s: sorted(x.strip().strip('"') for x in s.split(",") if x.strip())
    assert norm(extra[0]) == norm(extra[1])
