# -*- coding: utf-8 -*-
"""CLI 在非 UTF-8 控制台（Windows 默认 cp1252 / CI 重定向管道）下也不能崩。

回归背景：GitHub 的 windows runner 控制台代码页是 1252，打印中文日志会直接
UnicodeEncodeError 把打包脚本打断，所以 stdio 一律强制 UTF-8。
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"


def _run(args, encoding):
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = encoding
    env["PYTHONPATH"] = str(SRC) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run([sys.executable, *args], capture_output=True, env=env,
                          cwd=str(SRC.parent))


def test_cli_help_survives_cp1252_console():
    p = _run(["-m", "video2script.cli", "--help"], "cp1252")
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")
    out = p.stdout.decode("utf-8", "replace")     # 输出按 UTF-8 编码
    assert "视频" in out and "--diarize" in out


def test_cli_error_path_survives_cp1252_console(tmp_path):
    missing = tmp_path / "不存在.mp4"
    p = _run(["-m", "video2script.cli", str(missing)], "cp1252")
    assert p.returncode == 2
    assert "找不到文件" in p.stderr.decode("utf-8", "replace")


def test_gui_help_survives_cp1252_console():
    p = _run(["-m", "video2script.gui", "--help"], "cp1252")
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")
    assert "--port" in p.stdout.decode("utf-8", "replace")


# ---------------- scripts/ 下的工具脚本（回归：windows runner 上 make_icon 就是这么崩的）

def test_scripts_stdio_helper_survives_cp1252():
    code = ("import sys; sys.path.insert(0, r'%s'); from _stdio import force_utf8; "
            "force_utf8(); print('视频 → 文稿 ✓')" % (ROOT / "scripts"))
    env = dict(os.environ, PYTHONIOENCODING="cp1252")
    p = subprocess.run([sys.executable, "-c", code], capture_output=True, env=env)
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")
    assert "视频 → 文稿 ✓" in p.stdout.decode("utf-8")


def test_make_icon_runs_under_cp1252(tmp_path):
    """图标脚本在 cp1252 控制台下必须跑得完（会打印中文间距自检）。"""
    pytest.importorskip("PIL", reason="需要 dev extra 里的 pillow")
    env = dict(os.environ, PYTHONIOENCODING="cp1252")
    p = subprocess.run([sys.executable, str(ROOT / "scripts" / "make_icon.py"),
                        "--outdir", str(tmp_path)],
                       capture_output=True, env=env, cwd=str(tmp_path))
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")
    assert (tmp_path / "icon.png").stat().st_size > 1000
    assert (tmp_path / "icon.ico").stat().st_size > 1000
    assert "间距" in p.stdout.decode("utf-8", "replace")


def test_build_exe_help_survives_cp1252(tmp_path):
    """打包脚本 --help 在 cp1252 下也要正常（同一类崩溃）。"""
    env = dict(os.environ, PYTHONIOENCODING="cp1252")
    p = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_exe.py"), "--help"],
                       capture_output=True, env=env, cwd=str(tmp_path))
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")
