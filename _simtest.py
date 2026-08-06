# -*- coding: utf-8 -*-
"""集成逻辑模拟测试：用桩模块伪装 astrbot.api，加载真实 main.py 并推进 handler，
验证「解析 → 渲染 GIF → 发送图片 → 公布获奖者」全流程。"""
import asyncio
import importlib.util
import os
import sys
import types

sys.stdout.reconfigure(encoding="utf-8")

# ---------------- 桩：astrbot.api ----------------
def _mod(name):
    m = types.ModuleType(name)
    sys.modules[name] = m
    return m


class FakeLogger:
    def info(self, *a, **k): print("  [log] info:", a[0] if a else "")
    def error(self, *a, **k): print("  [log] error:", a[0] if a else "")


_api = _mod("astrbot.api")
_api.logger = FakeLogger()

_event = _mod("astrbot.api.event")
_event.filter = types.SimpleNamespace(command=lambda name, alias=None: (lambda fn: fn))
_event.AstrMessageEvent = object

_star = _mod("astrbot.api.star")
_star.Context = object


class _FakeStar:
    def __init__(self, context):
        self.context = context


_star.Star = _FakeStar
_star.register = lambda *a, **k: (lambda cls: cls)

# ---------------- 加载真实 main.py ----------------
# 以包方式加载（模拟 AstrBot 将插件目录作为包导入），使 from . import wheel 可用
_plugin_dir = os.path.dirname(os.path.abspath(__file__))
_pkg = types.ModuleType("astrbot_plugin_lottery")
_pkg.__path__ = [_plugin_dir]
_pkg.__package__ = "astrbot_plugin_lottery"
sys.modules["astrbot_plugin_lottery"] = _pkg

main = importlib.import_module("astrbot_plugin_lottery.main")


class R:
    def __init__(self, **k):
        self.__dict__.update(k)


class FakeEvent:
    def __init__(self, message_str):
        self.message_str = message_str
        self.results = []

    def plain_result(self, text):
        r = R(text=text)
        self.results.append(r)
        return r

    def image_result(self, path):
        r = R(path=path)
        self.results.append(r)
        return r


async def drive(handler):
    out = []
    try:
        while True:
            out.append(await anext(handler))
    except StopAsyncIteration:
        pass
    return out


async def main_run():
    failed = []
    from PIL import Image

    plugin = main.LotteryPlugin(object())
    ev = FakeEvent("/lucky 小明 小红 小刚 小丽")
    results = await drive(plugin.lucky(ev))

    assert len(results) == 2, f"应产生 2 个结果，实际 {len(results)}"
    img = results[0]
    assert img.path.endswith(".gif") and os.path.exists(img.path), "GIF 路径缺失"
    with Image.open(img.path) as im:
        frames = im.n_frames
    txt = results[1].text
    print("  [ok] 收到 2 个结果：image + plain")
    print(f"  [ok] GIF 存在，{frames} 帧，"
          f"{os.path.getsize(img.path)/1024:.0f} KB")
    print(f"  [ok] 公布文案：{txt.splitlines()[1]}")

    # 无参数 → 用法提示
    ev2 = FakeEvent("/lucky")
    res2 = await drive(plugin.lucky(ev2))
    assert res2 and "用法" in res2[0].text, res2
    print("  [ok] 无参数给出用法提示")

    # 超过上限 → 报错
    too_many = " ".join(f"人{i}" for i in range(1, 25))
    res3 = await drive(plugin.lucky(FakeEvent(f"/lucky {too_many}")))
    assert "最多" in res3[0].text, res3
    print("  [ok] 超人数上限报错")

    # 单个参赛者 → 报错
    res4 = await drive(plugin.lucky(FakeEvent("/lucky 仅一人")))
    assert "至少需要" in res4[0].text, res4
    print("  [ok] 不足 2 人报错")

    if failed:
        sys.exit(1)
    print("\n集成模拟：全部通过")


if __name__ == "__main__":
    asyncio.run(main_run())
