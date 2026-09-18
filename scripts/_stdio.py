# -*- coding: utf-8 -*-
"""脚本共用的 stdio 处理。

Windows 控制台默认代码页是 1252、CI 里 stdout 又是重定向管道，中文日志会直接
``UnicodeEncodeError`` 把脚本打断（真实的翻车记录：GitHub windows runner 上打不出
"角标↔文稿行最小间距"）。所有 scripts/ 下的脚本开头都调用 force_utf8()。
"""
from __future__ import annotations

import sys


def force_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            pass


# 被当作模块 import 时也顺手生效
force_utf8()
