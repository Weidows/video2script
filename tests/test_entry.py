# -*- coding: utf-8 -*-
"""统一入口的测试：CLI / GUI 合并在一个命令里，无参数 = GUI。"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from video2script.main import _strip, decide_mode  # noqa: E402


@pytest.mark.parametrize("argv,expected", [
    ([], "gui"),                                              # 双击 exe / cmd
    (["--open"], "gui"),                                      # GUI 专属参数
    (["--port", "9000"], "gui"),
    (["--host=0.0.0.0"], "gui"),
    (["--gui"], "gui"),
    (["--gui", "会议.mp4"], "gui"),                           # 预载文件
    (["会议.mp4"], "cli"),
    (["会议.mp4", "--level", "3"], "cli"),
    (["--help"], "cli"),                                      # 帮助走 CLI，语义明确
    (["--gui", "--help"], "gui"),
    (["--cli"], "cli"),                                       # 显式强制 CLI
    (["--gui", "--cli"], "cli"),                              # --cli 优先
])
def test_decide_mode(argv, expected):
    assert decide_mode(argv) == expected


def test_strip_removes_dispatch_flags_only():
    assert _strip(["--cli", "a.mp4", "--gui", "--level", "2"], "--gui", "--cli") \
        == ["a.mp4", "--level", "2"]


def test_version_flag_prints_version(capsys):
    from video2script import __version__
    from video2script.main import main
    assert main(["--version"]) == 0
    out = capsys.readouterr().out
    assert __version__ in out and "video2script" in out


def test_cli_mode_reports_missing_file(tmp_path, capsys):
    from video2script.main import main
    missing = tmp_path / "nope.mp4"
    assert main([str(missing)]) == 2          # 走 CLI 分支，文件不存在
    assert "找不到文件" in capsys.readouterr().err


def test_assets_are_present_and_nonempty():
    """图标要跟着仓库走：GUI favicon 与打包都读它（空文件会让 favicon 变 0 字节）。"""
    from video2script.config import ASSETS_DIR
    assert ASSETS_DIR.is_dir(), f"缺少资源目录 {ASSETS_DIR}：先跑 scripts/make_icon.py"
    for name in ("icon.png", "icon.ico"):
        p = ASSETS_DIR / name
        assert p.exists(), f"缺少 {name}"
        assert p.stat().st_size > 1000, f"{name} 只有 {p.stat().st_size} 字节，可疑"
