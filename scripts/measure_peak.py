# -*- coding: utf-8 -*-
"""测量 video2script 子进程的峰值内存（Windows psapi）。"""
import ctypes
import ctypes.wintypes as wt
import subprocess
import sys
import time
from pathlib import Path

psapi = ctypes.WinDLL("psapi", use_last_error=True)


class PMC(ctypes.Structure):
    _fields_ = [("cb", wt.DWORD), ("PageFaultCount", wt.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t)]


def peak_mb(pid: int) -> float:
    c = PMC()
    c.cb = ctypes.sizeof(PMC)
    h = ctypes.windll.kernel32.OpenProcess(0x1000 | 0x0400, False, pid)  # QUERY_INFO|VM_READ
    if not h:
        return -1.0
    try:
        if psapi.GetProcessMemoryInfo(h, ctypes.byref(c), c.cb):
            return c.PeakWorkingSetSize / 1024 / 1024
    finally:
        ctypes.windll.kernel32.CloseHandle(h)
    return -1.0


def main():
    repo = Path(sys.argv[1]).resolve()
    model = sys.argv[2] if len(sys.argv) > 2 else "medium"
    video = repo / "samples" / "say_zh.mp4"
    py = repo / ".venv" / "Scripts" / "python.exe"
    out = repo / "samples" / f"mem_{model}"
    cmd = [str(py), "-m", "video2script.cli", str(video), "--lang", "zh",
           "--model", model, "--level", "2", "-q", "-o", str(out)]
    t0 = time.time()
    p = subprocess.Popen(cmd, cwd=str(repo), stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    peak = 0.0
    while p.poll() is None:
        peak = max(peak, peak_mb(p.pid))
        time.sleep(0.5)
    dt = time.time() - t0
    print(f"model={model}  exit={p.returncode}  wall={dt:.1f}s  "
          f"peak_working_set={peak:.0f} MB")
    report = out / "report.json"
    if report.exists():
        import json
        d = json.loads(report.read_text(encoding="utf-8"))
        print("  duration:", d["duration_s"], "s  counts:", d["counts"])


if __name__ == "__main__":
    main()
