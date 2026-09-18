# -*- coding: utf-8 -*-
"""GUI 的独立入口：PyInstaller 需要一个绝对导入的顶层脚本。"""
from video2script.gui import main

if __name__ == "__main__":
    raise SystemExit(main())
