#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成应用图标（无外部素材，纯 Pillow 绘制）。

    python scripts/make_icon.py            # 生成 icon.png / icon.ico
    python scripts/make_icon.py --preview  # 另存小尺寸预览拼图，便于核对可辨识度

产出（单一真源，README / GUI favicon / PyInstaller 都引用这里）：
    src/video2script/assets/icon.png    512×512，透明圆角
    src/video2script/assets/icon.ico    16~256 多尺寸，小尺寸用简化构图单独绘制

构图：蓝紫渐变圆角块 + 声波 + 文稿行 + 播放角标 —— "声音/视频 → 文稿"。
小尺寸（≤32px）自动去掉声波、加粗文稿行、放大播放角标，否则缩放到 16px 会糊成一团。
"""
from __future__ import annotations

import io
import struct
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "src" / "video2script" / "assets"
S = 1024
BG_TOP = (79, 140, 255)       # #4F8CFF
BG_BOTTOM = (122, 92, 255)    # #7A5CFF
BADGE = (23, 32, 58)
WHITE = (255, 255, 255, 255)

ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]



def gradient(size: int) -> Image.Image:
    g = Image.new("RGB", (1, size))
    for y in range(size):
        t = y / (size - 1)
        g.putpixel((0, y), tuple(round(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOTTOM)))
    return g.resize((size, size), Image.NEAREST)


def rounded_mask(size: int, radius: int) -> Image.Image:
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return m


def _badge(d: ImageDraw.ImageDraw, cx: int, cy: int, r: int) -> None:
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(*BADGE, 255))
    t = int(r * 0.46)
    d.polygon([(cx - t * 0.7, cy - t), (cx - t * 0.7, cy + t), (cx + t * 0.95, cy)], fill=WHITE)


LAYOUT = {   # 单位：1024 设计基准下的 u；badge=(cx, cy, r)，bars=[(y, h, w), ...]
    "full":   {"bars": [(470, 86, 600), (612, 86, 340)], "badge": (772, 782, 132)},
    "simple": {"bars": [(330, 104, 560), (500, 104, 300)], "badge": (740, 700, 175)},
    "tiny":   {"bars": [(250, 130, 400)], "badge": (700, 700, 155)},
}
X0 = 190


def gap_to_badge(level: str) -> int:
    """角标圆与文稿行矩形之间的最小间距（u，1024 基准下），解析计算。"""
    lay = LAYOUT[level]
    cx, cy, r = lay["badge"]
    best = 10 ** 9
    for (y, h, w) in lay["bars"]:
        # 矩形上离圆心最近的点
        nx = min(max(cx, X0), X0 + w)
        ny = min(max(cy, y), y + h)
        best = min(best, ((cx - nx) ** 2 + (cy - ny) ** 2) ** 0.5 - r)
    return round(best)


def draw(px: int, level: str | None = None) -> Image.Image:
    """在 px×px 画布上绘制图标。level: full / simple / tiny（默认按尺寸自动选）。"""
    if level is None:
        level = "full" if px >= 48 else ("simple" if px > 24 else "tiny")
    img = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    img.paste(gradient(px).convert("RGBA"), (0, 0), rounded_mask(px, int(px * 0.22)))
    d = ImageDraw.Draw(img)
    u = px / 1024.0                                   # 以 1024 为设计基准
    x0 = round(X0 * u)
    lay = LAYOUT[level]

    def bar(y: int, h: int, w: int) -> None:
        d.rounded_rectangle([x0, round(y * u), x0 + round(w * u), round((y + h) * u)],
                            radius=round(h * u) // 2, fill=WHITE)

    if level == "full":
        # 声波：4 根对齐同一基线的竖条，高度有起伏
        bw, step = round(52 * u), round(104 * u)
        base = round(388 * u)
        for i, k in enumerate((0.62, 1.0, 0.78, 1.25)):
            h = round(86 * u * k)
            x = x0 + i * step
            d.rounded_rectangle([x, base - h, x + bw, base], radius=bw // 2, fill=WHITE)

    for (y, h, w) in lay["bars"]:
        bar(y, h, w)
    cx, cy, r = lay["badge"]
    _badge(d, round(cx * u), round(cy * u), round(r * u))
    return img


def write_ico(path: Path, frames: list[Image.Image]) -> None:
    """手写 ICO：每个尺寸用自己渲染的 PNG 帧，Pillow 的 sizes 参数只会缩放同一张图。"""
    frames = sorted(frames, key=lambda im: im.width)
    header = struct.pack("<HHH", 0, 1, len(frames))
    entries, blobs, offset = b"", b"", 6 + 16 * len(frames)
    for im in frames:
        buf = io.BytesIO()
        im.save(buf, format="PNG", optimize=True)
        blob = buf.getvalue()
        n = 0 if im.width >= 256 else im.width
        entries += struct.pack("<BBBBHHII", n, n, 0, 0, 1, 32, len(blob), offset)
        blobs += blob
        offset += len(blob)
    path.write_bytes(header + entries + blobs)


def main() -> int:
    ASSETS.mkdir(parents=True, exist_ok=True)
    master = draw(S, level="full")
    png = ASSETS / "icon.png"
    master.resize((512, 512), Image.LANCZOS).save(png, optimize=True)

    frames = [draw(sz) for sz in ICO_SIZES]           # 每个尺寸按自己的档位重绘
    ico = ASSETS / "icon.ico"
    write_ico(ico, frames)

    frames[ICO_SIZES.index(32)].save(ASSETS / "icon-32.png", optimize=True)
    frames[ICO_SIZES.index(16)].save(ASSETS / "icon-16.png", optimize=True)

    print(f"written: {png} ({png.stat().st_size} B)")
    print(f"written: {ico} ({ico.stat().st_size} B, sizes={ICO_SIZES})")

    for lvl in ("full", "simple", "tiny"):
        g = gap_to_badge(lvl)
        print(f"  {lvl:<6} 角标↔文稿行最小间距 {g}u "
              f"(16px 下 {g * 16 / 1024:.1f}px, 32px 下 {g * 32 / 1024:.1f}px)")

    if "--preview" in sys.argv:
        tiles = []
        for px in (256, 64, 32, 16):
            im = draw(px)
            zoom = max(1, 256 // px)
            tiles.append(im.resize((px * zoom, px * zoom), Image.NEAREST))
        w = sum(t.width for t in tiles) + 20 * (len(tiles) - 1)
        sheet = Image.new("RGBA", (w, 256), (255, 255, 255, 255))
        x = 0
        for t in tiles:
            sheet.paste(t, (x, 0), t)
            x += t.width + 20
        out = ASSETS / "_preview.png"
        sheet.save(out)
        print(f"preview: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
