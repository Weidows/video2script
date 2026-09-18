# -*- coding: utf-8 -*-
"""``python -m video2script`` 入口（绝对导入，PyInstaller 打包也用它）。"""
from video2script.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
