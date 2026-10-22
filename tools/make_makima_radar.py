"""生成「玛奇玛人设维度雷达图」。

依赖：Pillow（不属于机器人运行依赖，仅用于生成文档配图）。
用法：
    python tools/make_makima_radar.py
输出：
    docs/images/makima_radar.png
"""

from __future__ import annotations

import math
import os

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "images", "makima_radar.png")

W, H = 1600, 1580
CX, CY, R = 800, 848, 450

BG = (247, 243, 236)
INK = (28, 26, 25)
MUTED = (122, 113, 104)
GRID = (222, 213, 201)
GRID_MAIN = (200, 189, 174)
CRIMSON = (176, 40, 38)
DEEP = (56, 22, 20)

DIMS = ["魅力", "攻击性", "温柔", "阳光", "体贴", "神秘感", "控制欲", "危险感", "冷静", "距离感"]
SURFACE = [9.5, 3.0, 8.5, 4.0, 8.5, 7.0, 5.0, 3.0, 9.5, 4.0]
INNER = [9.5, 9.0, 5.0, 2.0, 6.0, 10.0, 10.0, 9.5, 10.0, 9.0]

BOLD = "C:/Windows/Fonts/msyhbd.ttc"
REG = "C:/Windows/Fonts/msyh.ttc"


def polar(i: int, n: int, r: float) -> tuple[float, float]:
    a = math.radians(-90 + i * 360.0 / n)
    return CX + r * math.cos(a), CY + r * math.sin(a)


def dashed_line(draw, p1, p2, fill, width, dash=16, gap=11):
    x1, y1 = p1
    x2, y2 = p2
    total = math.hypot(x2 - x1, y2 - y1)
    if total == 0:
        return
    dx, dy = (x2 - x1) / total, (y2 - y1) / total
    pos = 0.0
    while pos < total:
        end = min(pos + dash, total)
        draw.line([(x1 + dx * pos, y1 + dy * pos), (x1 + dx * end, y1 + dy * end)], fill=fill, width=width)
        pos = end + gap


def polygon_points(values, n, scale):
    return [polar(i, n, values[i] / 10.0 * scale) for i in range(n)]


def main() -> None:
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    f_title = ImageFont.truetype(BOLD, 60)
    f_sub = ImageFont.truetype(REG, 27)
    f_label = ImageFont.truetype(BOLD, 33)
    f_ring = ImageFont.truetype(REG, 20)
    f_legend = ImageFont.truetype(REG, 29)
    f_note = ImageFont.truetype(REG, 22)

    # ---- 标题 ----
    draw.text((CX, 92), "玛奇玛 · 人设维度雷达图", font=f_title, fill=INK, anchor="mm")
    draw.text((CX, 156), "《电锯人》角色蒸馏 ｜ 表层呈现 vs 内里本质（0–10 分）", font=f_sub, fill=MUTED, anchor="mm")
    draw.line([(CX - 240, 196), (CX + 240, 196)], fill=CRIMSON, width=2)

    n = len(DIMS)

    # ---- 网格环 ----
    for step in range(2, 11, 2):
        r = R * step / 10.0
        pts = [polar(i, n, r) for i in range(n)]
        draw.line(pts + [pts[0]], fill=GRID_MAIN if step == 10 else GRID, width=2 if step == 10 else 1)

    # ---- 轴线 ----
    for i in range(n):
        draw.line([(CX, CY), polar(i, n, R)], fill=GRID, width=1)

    # ---- 刻度值 ----
    for step in range(2, 11, 2):
        r = R * step / 10.0
        draw.text((CX + 12, CY - r), str(step), font=f_ring, fill=(168, 158, 146), anchor="lm")

    # ---- 内里本质（深色，虚线）----
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    inner_pts = polygon_points(INNER, n, R)
    od.polygon(inner_pts, fill=DEEP + (46,))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)
    for i in range(n):
        dashed_line(draw, inner_pts[i], inner_pts[(i + 1) % n], DEEP, 4)

    # ---- 表层呈现（绯红，实线）----
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    surf_pts = polygon_points(SURFACE, n, R)
    od.polygon(surf_pts, fill=CRIMSON + (58,))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)
    draw.line(surf_pts + [surf_pts[0]], fill=CRIMSON, width=5)

    # ---- 顶点圆点 ----
    for i in range(n):
        x, y = surf_pts[i]
        draw.ellipse([x - 8, y - 8, x + 8, y + 8], fill=CRIMSON, outline=BG, width=2)
    for i in range(n):
        x, y = inner_pts[i]
        draw.ellipse([x - 7, y - 7, x + 7, y + 7], fill=DEEP, outline=BG, width=2)

    # ---- 维度标签 ----
    for i, name in enumerate(DIMS):
        lx, ly = polar(i, n, R + 62)
        ca = math.cos(math.radians(-90 + i * 360.0 / n))
        if ca > 0.25:
            anchor = "lm"
        elif ca < -0.25:
            anchor = "rm"
        else:
            anchor = "mm"
        draw.text((lx, ly), name, font=f_label, fill=INK, anchor=anchor)

    # ---- 图例 ----
    ly = 1478
    items = [
        ("surface", "表层呈现 · 她让你看到的"),
        ("inner", "内里本质 · 她真正的样子"),
    ]
    widths = []
    for kind, text in items:
        widths.append(46 + 16 + draw.textlength(text, font=f_legend))
    gap_between = 90
    total_w = sum(widths) + gap_between
    x = CX - total_w / 2
    for (kind, text), w in zip(items, widths):
        if kind == "surface":
            draw.line([(x, ly), (x + 46, ly)], fill=CRIMSON, width=6)
        else:
            dashed_line(draw, (x, ly), (x + 46, ly), DEEP, 6, dash=12, gap=9)
        draw.text((x + 46 + 16, ly), text, font=f_legend, fill=INK, anchor="lm")
        x += w + gap_between

    # ---- 脚注 ----
    draw.text(
        (CX, 1540),
        "评分为主观蒸馏刻度，用于快速把握角色张力，非官方设定。",
        font=f_note,
        fill=MUTED,
        anchor="mm",
    )

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    img.save(OUT, "PNG")
    print(f"saved: {OUT}")


if __name__ == "__main__":
    main()
