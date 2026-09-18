#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用 PyInstaller 打包成免安装可执行文件（不打包模型权重，首次运行自动下载）。

    python scripts/build_exe.py            # 当前平台
    python scripts/build_exe.py --onedir   # 目录版（启动更快）

产物：dist/video2script(.exe)、dist/video2script-gui(.exe)
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

try:
    from _stdio import force_utf8
except ImportError:  # 被其它脚本 import 时
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _stdio import force_utf8

force_utf8()

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--onedir", action="store_true", help="目录模式（默认单文件）")
    ap.add_argument("--keep", action="store_true", help="保留 build/ 中间产物")
    a = ap.parse_args()

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("先装打包依赖：pip install pyinstaller", file=sys.stderr)
        return 2

    mode = "--onedir" if a.onedir else "--onefile"
    icon = ROOT / "src" / "video2script" / "assets" / \
        ("icon.ico" if sys.platform == "win32" else "icon.png")
    args = [
        mode, "--noconfirm", "--clean",
        "--collect-all", "faster_whisper",   # 含 assets/silero VAD 的 onnx
        "--collect-all", "ctranslate2",
        "--collect-all", "tokenizers",
        "--collect-all", "av",
        "--collect-submodules", "onnxruntime",
        "--hidden-import", "huggingface_hub",
        "--paths", str(ROOT / "src"),
        "--add-data", f"{ROOT / 'src' / 'video2script' / 'assets'}{os.pathsep}video2script/assets",
        "--name", "video2script",
        # 绝对导入的入口；CLI 与 GUI 都在这里面（无参数 = GUI）
        str(ROOT / "src" / "video2script" / "__main__.py"),
    ]
    if icon.exists():
        args += ["--icon", str(icon)]
    else:
        print(f"! 没有图标文件 {icon}，先跑 python scripts/make_icon.py", file=sys.stderr)

    print(f"=== 打包（{platform.system()} / {platform.machine()}）")
    r = subprocess.run([sys.executable, "-m", "PyInstaller", *args], cwd=str(ROOT))
    if r.returncode != 0:
        print("打包失败", file=sys.stderr)
        return r.returncode

    if not a.keep:
        shutil.rmtree(ROOT / "build", ignore_errors=True)
        for spec in ROOT.glob("*.spec"):
            spec.unlink(missing_ok=True)

    print("\n完成，产物在 dist/：")
    for p in sorted((ROOT / "dist").iterdir()):
        print(f"  {p.name}  {p.stat().st_size / 1e6:.1f} MB")
    print("\n注意：模型权重没有打进去，首次运行会下载到 ~/.cache/video2script/models")
    print("用法：不带参数双击 = 网页 GUI；带文件参数 = 命令行转写")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
