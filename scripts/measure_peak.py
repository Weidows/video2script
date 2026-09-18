#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测量一次转写任务的资源占用（开发用）。

    pip install psutil
    python scripts/measure_peak.py . medium

注意：Windows 的 venv ``python.exe`` 是个转发 stub，真正的解释器是它的子进程，
所以要统计**整棵进程树**的 RSS，否则只会看到 5 MB。
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path


def tree_rss(proc) -> float:
    """进程树当前 RSS（MB）。"""
    import psutil
    total = 0.0
    procs = [proc]
    try:
        procs += proc.children(recursive=True)
    except Exception:
        pass
    for p in procs:
        try:
            total += p.memory_info().rss
        except Exception:
            pass
    return total / 1024 / 1024


def main() -> int:
    repo = Path(sys.argv[1]).resolve()
    model = sys.argv[2] if len(sys.argv) > 2 else "medium"
    extra = sys.argv[3:]
    video = repo / "samples" / "say_zh.mp4"
    py = repo / ".venv" / "Scripts" / "python.exe"
    if not py.exists():
        py = Path(sys.executable)
    out = repo / "samples" / f"mem_{model}"

    try:
        import psutil
    except ImportError:
        print("先装 psutil：pip install psutil", file=sys.stderr)
        return 2

    cmd = [str(py), "-m", "video2script.cli", str(video), "--lang", "zh",
           "--model", model, "--level", "2", "-q", "-o", str(out), *extra]
    t0 = time.time()
    p = psutil.Popen(cmd, cwd=str(repo), stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL)
    peak = 0.0
    while p.poll() is None:
        peak = max(peak, tree_rss(p))
        time.sleep(0.5)
    wall = time.time() - t0
    print(f"model={model}  exit={p.returncode}  wall={wall:.1f}s  "
          f"peak_rss(进程树,采样)={peak:.0f} MB")
    report = out / "report.json"
    if report.exists():
        import json
        d = json.loads(report.read_text(encoding="utf-8"))
        print(f"  audio={d['duration_s']}s  counts={d['counts']}")
    return p.returncode or 0


if __name__ == "__main__":
    raise SystemExit(main())
