# -*- coding: utf-8 -*-
"""转盘抽奖的纯逻辑与 Pillow GIF 渲染。

本模块刻意与 AstrBot 解耦：不导入任何 astrbot 包，便于独立测试与维护。
对外提供：
    MAX_NAMES               允许的最大参与人数
    parse_names(text)       从指令消息文本中解析昵称列表
    pick_winner(names, rng) 公平选出获奖者
    render_gif(names, winner, out)  渲染旋转 GIF，最后一帧停在获奖者处
"""
from __future__ import annotations

import math
import os
import random
import re
from typing import List, Optional, Sequence

from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------- 常量

MAX_NAMES = 20  # 参与人数上限：扇区过窄时昵称会互相重叠

CANVAS_W = 560          # 画布宽度
CANVAS_H = 760          # 画布高度
WHEEL_R = 280           # 转盘半径
WHEEL_CX = CANVAS_W // 2
WHEEL_CY = 400          # 转盘圆心（y）
POINTER_Y = WHEEL_CY - WHEEL_R  # 指针尖端 y（12 点方向，转盘最顶端）

# 扇形图层：方形且以圆心为中心，保证旋转时圆心不偏移
LAYER_SIZE = 2 * (WHEEL_R + 8)
LAYER_OFF_X = WHEEL_CX - LAYER_SIZE // 2
LAYER_OFF_Y = WHEEL_CY - LAYER_SIZE // 2

N_FRAMES = 34           # 旋转帧数
FRAME_MS = 120          # 旋转帧时长（毫秒），旋转总时长约 4s
HOLD_MS = 3200          # 末帧定格时长（毫秒），供查看获奖结果
MIN_TURNS, MAX_TURNS = 5, 8  # 旋转圈数范围
GIF_COLORS = 128        # GIF 调色板颜色数（显著减小体积）

PALETTE = [
    (255, 107, 107), (255, 217, 61), (107, 203, 119), (77, 150, 255),
    (255, 159, 69), (155, 89, 182), (26, 188, 156), (230, 126, 34),
]
GOLD = (255, 193, 7)
INK = (40, 40, 40)
BG = (250, 248, 244)

# 常见中文字体路径（Windows / macOS / Linux）
FONT_CANDIDATES = [
    "C:/Windows/Fonts/msyhbd.ttc",   # 微软雅黑 Bold
    "C:/Windows/Fonts/msyh.ttc",     # 微软雅黑
    "C:/Windows/Fonts/simhei.ttf",   # 黑体
    "C:/Windows/Fonts/simsun.ttc",   # 宋体
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
]
_FONT_PATH = next((p for p in FONT_CANDIDATES if os.path.exists(p)), None)

# 昵称分隔符：空格、半/全角逗号、顿号、分号
_NAME_SPLIT_RE = re.compile(r"[\s,，、;；]+")


# ---------------------------------------------------------------- 命令解析

# 支持的指令名 / 别名（与 main.py 中注册保持一致）
COMMANDS = ("lucky", "抽奖", "转盘")


def parse_names(message_str: str, commands: Sequence[str] = COMMANDS) -> List[str]:
    """从指令消息文本中解析昵称列表（去掉指令词、去空白、去重、保序）。

    例如 ``"/lucky 小明,小红 小刚"`` -> ``["小明", "小红", "小刚"]``
    """
    raw = message_str.strip().lstrip("/")
    for cmd in commands:
        if raw == cmd or raw.startswith(cmd + " ") or raw.startswith(cmd + "\t"):
            raw = raw[len(cmd):]
            break
    return list(dict.fromkeys(
        x for x in _NAME_SPLIT_RE.split(raw.strip()) if x
    ))


# ---------------------------------------------------------------- 字体

def _make_font(size: int) -> ImageFont.ImageFont:
    """优先使用系统中文字体，找不到时回退到 PIL 内置字体。"""
    if _FONT_PATH:
        try:
            return ImageFont.truetype(_FONT_PATH, size)
        except Exception:
            pass
    return ImageFont.load_default()


# ---------------------------------------------------------------- 抽奖

def pick_winner(names: Sequence[str], rng: Optional[random.Random] = None) -> str:
    """等概率选出一位获奖者。默认使用系统随机源（不可预测，保证公平）。"""
    if not names:
        raise ValueError("参赛者列表不能为空")
    r = rng or random.SystemRandom()
    return names[r.randrange(len(names))]


# ---------------------------------------------------------------- 渲染

def _hole_radius(n: int) -> int:
    """中心轴孔半径：人数越多轴孔越大，为径向文字腾出横向空间。"""
    frac = 0.20 if n <= 4 else (0.22 if n <= 8 else (0.26 if n <= 14 else 0.30))
    return int(WHEEL_R * frac)


def _font_size(names: Sequence[str], hole: int) -> int:
    """自适应字号：受「径向可用长度」和「轴孔处扇区横向间隙」双重约束。"""
    n = len(names)
    step = 360.0 / n
    arc = hole * math.radians(step)          # 轴孔半径处的扇区弧长
    avail = WHEEL_R - hole - 16              # 径向可写文字的长度
    max_len = max((len(x) for x in names), default=1)
    return max(13, min(44, int(avail / max_len), int(arc * 0.85)))


def _render_name(name: str, font: ImageFont.ImageFont, color) -> Image.Image:
    """把单个昵称渲染成带深色描边、居中于透明图片的 RGBA 图。"""
    tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    bbox = tmp.textbbox((0, 0), name, font=font, stroke_width=2)
    if bbox is None:
        w = int(tmp.textlength(name, font=font)) + 10
        h = getattr(font, "size", 16) + 10
    else:
        w = int(bbox[2] - bbox[0]) + 10
        h = int(bbox[3] - bbox[1]) + 10
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.text((5, 5), name, font=font, fill=color,
           stroke_width=2, stroke_fill=(0, 0, 0, 170))
    return img


def _draw_wheel_layer(names: Sequence[str]) -> Image.Image:
    """绘制静态转盘图层（扇形 + 径向昵称 + 轴孔），后续按帧旋转此图层。"""
    n = len(names)
    step = 360.0 / n
    hole = _hole_radius(n)
    font = _make_font(_font_size(names, hole))
    layer = Image.new("RGBA", (LAYER_SIZE, LAYER_SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    c = LAYER_SIZE // 2

    for i, name in enumerate(names):
        start, end = i * step, (i + 1) * step
        color = PALETTE[i % len(PALETTE)] + (255,)
        d.pieslice([c - WHEEL_R, c - WHEEL_R, c + WHEEL_R, c + WHEEL_R],
                   start, end, fill=color)

        # 昵称沿扇区中线径向排列，从内向外阅读
        mid = start + step / 2
        rad = math.radians(mid)
        dx, dy = math.cos(rad), math.sin(rad)
        txt = _render_name(name, font, (255, 255, 255, 255))
        rot = txt.rotate(-mid, expand=True, resample=Image.BICUBIC)
        r_text = hole + (WHEEL_R - hole) * 0.58
        pos = (c - rot.width / 2 + dx * r_text, c - rot.height / 2 + dy * r_text)
        layer.alpha_composite(rot, (int(pos[0]), int(pos[1])))

    # 金色外圈 + 深色轴孔 + 轴心圆点
    d.ellipse([c - WHEEL_R, c - WHEEL_R, c + WHEEL_R, c + WHEEL_R],
              outline=GOLD, width=5)
    d.ellipse([c - hole, c - hole, c + hole, c + hole], fill=(45, 45, 45, 255))
    d.ellipse([c - 11, c - 11, c + 11, c + 11], fill=GOLD)
    return layer


def _make_base(spinning: bool, font_tip) -> Image.Image:
    """构建固定底图：标题 + 顶部指针 + 底部状态文字。"""
    base = Image.new("RGBA", (CANVAS_W, CANVAS_H), BG + (255,))
    d = ImageDraw.Draw(base)
    d.text((WHEEL_CX, 36), "转盘抽奖", font=_make_font(42), fill=INK, anchor="mm")

    # 指针：朝下的等腰三角形，尖端正对转盘最顶端
    apex = (WHEEL_CX, POINTER_Y - 14)
    base_l = (WHEEL_CX - 15, POINTER_Y + 9)
    base_r = (WHEEL_CX + 15, POINTER_Y + 9)
    d.polygon([apex, base_l, base_r], fill=(216, 56, 56, 255))
    d.ellipse([WHEEL_CX - 6, POINTER_Y - 20, WHEEL_CX + 6, POINTER_Y - 8],
              fill=(216, 56, 56, 255))

    if spinning:
        d.text((WHEEL_CX, CANVAS_H - 36), "抽奖中…", font=font_tip,
               fill=(150, 150, 150), anchor="mm")
    return base


def _final_frame(rot_layer: Image.Image, names: Sequence[str],
                 winner: str) -> Image.Image:
    """最后一张帧：叠加金色高亮扇区 + 底部金色获奖横幅。"""
    n = len(names)
    step = 360.0 / n
    base = _make_base(False, None)
    base.paste(rot_layer, (LAYER_OFF_X, LAYER_OFF_Y), rot_layer)

    # 获奖扇区固定在顶部（12 点方向），半透明金色高亮
    if step < 180:
        overlay = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        start, end = 270 - step / 2, 270 + step / 2
        od.pieslice([WHEEL_CX - WHEEL_R, WHEEL_CY - WHEEL_R,
                     WHEEL_CX + WHEEL_R, WHEEL_CY + WHEEL_R],
                    start, end, fill=(255, 215, 0, 130))
        base = Image.alpha_composite(base, overlay)

    # 金色横幅：获奖者
    d = ImageDraw.Draw(base)
    bw = 420
    bx0, by0 = WHEEL_CX - bw // 2, CANVAS_H - 70
    d.rounded_rectangle([bx0, by0, bx0 + bw, by0 + 52], radius=16,
                        fill=GOLD + (255,), outline=(180, 120, 0), width=2)
    d.text((WHEEL_CX, by0 + 26), f"获奖者：{winner}", font=_make_font(30),
           fill=(60, 40, 0), anchor="mm")
    return base.convert("RGB")


def render_gif(names: Sequence[str], winner: str,
               output_path: str) -> str:
    """渲染旋转 GIF：先快速转动、逐步减速，最终停在 winner 扇区并高亮定格。"""
    n = len(names)
    if n < 1 or n > MAX_NAMES:
        raise ValueError(f"参与人数需在 1~{MAX_NAMES} 之间")
    if winner not in names:
        raise ValueError("winner 不在参赛者列表中")

    idx = names.index(winner)
    mid = idx * (360.0 / n) + (360.0 / n) / 2      # 获奖扇区在转盘局部坐标系的中线角
    target_rot = (270 - mid) % 360                 # 使该中线正好转到顶部指针处
    total = target_rot + random.SystemRandom().randint(MIN_TURNS, MAX_TURNS) * 360

    def ease(t: float) -> float:                   # easeOutCubic：快起慢停
        return 1 - (1 - t) ** 3

    layer = _draw_wheel_layer(names)
    tip_font = _make_font(20)

    frames: List[Image.Image] = []
    durations: List[int] = []
    for f in range(N_FRAMES):
        rot = total * ease(f / (N_FRAMES - 1))
        # 旋转帧用最近邻（扇区边缘锐利、利于 GIF 压缩）；末帧用双三次保证文字清晰
        resample = Image.BICUBIC if f == N_FRAMES - 1 else Image.NEAREST
        rot_layer = layer.rotate(-rot, resample=resample)
        if f == N_FRAMES - 1:
            frames.append(_final_frame(rot_layer, names, winner))
            durations.append(HOLD_MS)          # 末帧长时间定格，供查看获奖结果
        else:
            base = _make_base(True, tip_font)
            base.paste(rot_layer, (LAYER_OFF_X, LAYER_OFF_Y), rot_layer)
            frames.append(base.convert("RGB"))
            durations.append(FRAME_MS)

    # 逐帧量化为 128 色调色板，显著减小文件体积
    quantize_method = getattr(getattr(Image, "Quantize", None), "MEDIANCUT", None)
    if quantize_method is None:
        quantize_method = getattr(Image, "MEDIANCUT", None)
    if quantize_method is None:
        raise RuntimeError("当前 Pillow 不支持 MEDIANCUT 量化")
    quantized = [fr.quantize(colors=GIF_COLORS, method=quantize_method)
                 for fr in frames]
    quantized[0].save(output_path, save_all=True, append_images=quantized[1:],
                      duration=durations, loop=0, optimize=True)
    return output_path


# ---------------------------------------------------------------- 独立预览

if __name__ == "__main__":
    import sys
    import tempfile

    demo = sys.argv[1:] or ["小明", "小红", "小刚", "小丽", "阿伟", "露娜"]
    w = pick_winner(demo)
    out = os.path.join(tempfile.gettempdir(), "wheel_preview.gif")
    render_gif(demo, w, out)
    print(f"winner = {w}")
    print(f"gif    = {out}")
    print(f"size   = {os.path.getsize(out) / 1024:.0f} KB, 人数 = {len(demo)}")
