# -*- coding: utf-8 -*-
"""本地自检：验证 parse_names 与 render_gif（不依赖 AstrBot 环境）。"""
import os
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")

import wheel  # noqa: E402
from PIL import Image  # noqa: E402

failed = []


def check(name: str, cond: bool, detail: str = ""):
    if cond:
        print(f"  [OK] {name}")
    else:
        failed.append(name)
        print(f"  [FAIL] {name} {detail}")


print("== parse_names ==")
check("lucky 基本", wheel.parse_names("/lucky 小明 小红 小刚") == ["小明", "小红", "小刚"],
      wheel.parse_names("/lucky 小明 小红 小刚"))
check("别名抽奖", wheel.parse_names("/抽奖 小明，小红、小刚") == ["小明", "小红", "小刚"],
      wheel.parse_names("/抽奖 小明，小红、小刚"))
check("无参指令", wheel.parse_names("/lucky") == [], wheel.parse_names("/lucky"))
check("去重保序", wheel.parse_names("/lucky 小明 小明 小刚") == ["小明", "小刚"],
      wheel.parse_names("/lucky 小明 小明 小刚"))
check("超长空白", wheel.parse_names("/lucky    小明  小红  ") == ["小明", "小红"],
      wheel.parse_names("/lucky    小明  小红  "))
check("命令词不在开头保留", wheel.parse_names("lucky小明") == ["lucky小明"],
      wheel.parse_names("lucky小明"))

print("== render_gif ==")
orig_font_path = wheel._FONT_PATH
wheel._FONT_PATH = None
try:
    font = wheel._make_font(16)
    img = wheel._render_name("兼容测试", font, (255, 255, 255, 255))
    check("默认字体回退可渲染", img.size[0] > 0 and img.size[1] > 0, img.size)
finally:
    wheel._FONT_PATH = orig_font_path

names = ["小明", "小红", "小刚", "小丽", "阿伟", "露娜", "胖虎", "静香", "大雄", "丸子"]
winner = "静香"
out = os.path.join(tempfile.gettempdir(), "lottery_selftest.gif")
wheel.render_gif(names, winner, out)
size_kb = os.path.getsize(out) / 1024
im = Image.open(out)
check(f"文件大小 {size_kb:.0f}KB < 1200KB", size_kb < 1200)
check("帧数 = N_FRAMES", im.n_frames == wheel.N_FRAMES, im.n_frames)
check("尺寸 560x760", im.size == (wheel.CANVAS_W, wheel.CANVAS_H), im.size)

# 末帧顶部像素应近似等于「获奖扇区色 × 0.49 + 金色高亮 × 0.51」
im.seek(im.n_frames - 1)
fin = im.convert("RGB")
n = len(names)
step = 360.0 / n
px = fin.getpixel((wheel.WHEEL_CX, wheel.WHEEL_CY - wheel.WHEEL_R + 8))
base_col = wheel.PALETTE[names.index(winner)]
expect = tuple(int(round(base_col[i] * 0.49 + (255, 215, 0)[i] * 0.51)) for i in range(3))
check("末帧获奖扇区停在顶部指针下", px == expect, f"got={px} expect={expect}")

# 边界：单人与最大人数
for cnt in (1, 2, wheel.MAX_NAMES):
    nn = [f"选手{i}" for i in range(1, cnt + 1)]
    w = wheel.pick_winner(nn)
    p = os.path.join(tempfile.gettempdir(), f"lottery_{cnt}.gif")
    wheel.render_gif(nn, w, p)
    check(f"边界 {cnt} 人渲染", os.path.getsize(p) > 0)

# 边界：非法输入
try:
    wheel.render_gif([], "x", out)
    check("0 人应报错", False)
except ValueError:
    check("0 人应报错", True)

print()
if failed:
    print("结果：", len(failed), "项失败")
    sys.exit(1)
print("结果：全部通过")
