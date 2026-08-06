# -*- coding: utf-8 -*-
"""AstrBot 转盘抽奖插件。

用法：``/lucky 昵称1 昵称2 ...``（别名：``/抽奖``、``/转盘``）
机器人会生成一个等距放置所有昵称的旋转转盘 GIF，减速停止后定格在获奖者
扇区并公布获奖者。昵称之间用空格或中英文逗号/顿号分隔，最多 20 人。
"""
from __future__ import annotations

import asyncio
import functools
import os
import tempfile
import uuid

from astrbot.api import logger
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register

from . import wheel

# 与 wheel.COMMANDS 保持一致（wheel 负责把指令词从消息里剥掉）
_ALIAS = set(wheel.COMMANDS) - {"lucky"}


def _cleanup_gif(path: str | None) -> None:
    """删除已生成的临时 GIF，避免 temp 目录持续累积。"""
    if not path:
        return
    try:
        os.remove(path)
    except FileNotFoundError:
        return
    except OSError as exc:
        logger.warning(f"[转盘抽奖] 清理 GIF 失败: {exc}")


@register(
    "astrbot_plugin_lottery",
    "曹扬",
    "群聊转盘抽奖：一条指令输入任意数量昵称，转盘旋转停止后公布获奖者",
    "1.0.0",
)
class LotteryPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    @filter.command("lucky", alias=_ALIAS)
    async def lucky(self, event: AstrMessageEvent):
        """群聊转盘抽奖：/lucky 昵称1 昵称2 ...（空格或逗号分隔）"""
        names = wheel.parse_names(event.message_str)

        if not names:
            yield event.plain_result(
                "​用法：/lucky 昵称1 昵称2 …\n"
                "例如：/lucky 小明 小红 小刚\n"
                "昵称用空格或中英文逗号、顿号分隔，最多 20 人。"
            )
            return
        if len(names) > wheel.MAX_NAMES:
            yield event.plain_result(
                f"​参与人数过多（{len(names)}），最多支持 {wheel.MAX_NAMES} 人。"
            )
            return
        if len(names) < 2:
            yield event.plain_result("​至少需要 2 名参赛者才能开始抽奖。")
            return

        winner = wheel.pick_winner(names)
        logger.info(f"[转盘抽奖] 参赛者={names} 获奖者={winner}")

        # 渲染 GIF 是 CPU 密集操作，放入线程池避免阻塞 AstrBot 事件循环
        gif_path = os.path.join(tempfile.gettempdir(), f"lottery_{uuid.uuid4().hex}.gif")
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(
                None,
                functools.partial(
                    wheel.render_gif,
                    names=names,
                    winner=winner,
                    output_path=gif_path,
                ),
            )
        except Exception as e:
            err_id = uuid.uuid4().hex[:8]
            logger.error(f"[转盘抽奖] 渲染失败 (id={err_id}): {e}", exc_info=True)
            _cleanup_gif(gif_path)
            yield event.plain_result(f"​转盘渲染失败，请稍后重试。错误 ID：{err_id}")
            return

        try:
            # 先发转盘动画 GIF，再公布获奖者
            yield event.image_result(gif_path)
            yield event.plain_result(
                "​🎉 抽奖结果 🎉\n"
                f"🏆 获奖者：{winner}\n"
                f"参赛者：{'、'.join(names)}"
            )
        finally:
            _cleanup_gif(gif_path)
