# -*- coding: utf-8 -*-
"""统一入口：CLI 与 GUI 合并在同一个 `video2script` 命令里。

    video2script                     # 不带参数 → 启动本地网页 GUI
    video2script meeting.mp4 …       # 给文件 → 命令行转写
    video2script --gui [video]       # 强制 GUI，可顺带把文件预载进去
    video2script --cli …             # 强制 CLI（脚本里保证语义明确用）
    video2script-gui / python -m video2script.gui   # 仍然可用（兼容保留）

GUI 的网页服务只监听 127.0.0.1，CLI 模式不启动任何服务。
"""
from __future__ import annotations

import sys

VERSION_FLAGS = ("-V", "--version")
# 这些是 GUI 专属参数，出现即视为要开界面
GUI_HINTS = ("--open", "--host", "--port")


def decide_mode(argv: list[str]) -> str:
    """决定这次跑 CLI 还是 GUI —— 纯函数，方便测试。

    规则（可预期优先）：
      * 完全不带参数 → GUI（双击 exe / 双击 cmd 的场景）
      * 带 ``--gui`` 或 GUI 专属参数（``--open`` / ``--host`` / ``--port``）→ GUI
      * ``--cli`` 优先级最高，脚本里可强制走命令行
      * 其它（含 ``--help``、给了文件路径）→ CLI
    """
    args = list(argv)
    if "--cli" in args:
        return "cli"
    if "--gui" in args:
        return "gui"
    if not args:
        return "gui"
    if any(a.split("=")[0] in GUI_HINTS for a in args):
        return "gui"
    return "cli"


def _strip(args: list[str], *flags: str) -> list[str]:
    return [a for a in args if a not in flags]


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if any(a in argv for a in VERSION_FLAGS):
        from . import __version__
        print(f"video2script {__version__}")
        return 0

    if decide_mode(argv) == "gui":
        from .gui import main as gui_main
        return gui_main(_strip(argv, "--gui", "--cli"))

    from .cli import main as cli_main
    return cli_main(_strip(argv, "--gui", "--cli"))


if __name__ == "__main__":
    raise SystemExit(main())
