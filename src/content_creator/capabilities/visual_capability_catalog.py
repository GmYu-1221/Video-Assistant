"""Executable visual vocabulary exposed to the Director in natural language."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

DIRECTOR_VISUAL_CAPABILITIES: dict[str, list[dict[str, Any]]] = {
    "entrance": [
        {"name": "card_flip_reveal", "description": "图片以三维卡片翻转的方式进入画面。", "examples": ["页面翻转进入", "卡片翻面出现", "3D翻转入场"]},
        {"name": "glitch_reveal", "description": "图片通过受控的数字故障、扫描和信号错位逐步显现。", "examples": ["数字故障进入", "扫描线显现", "信号错位出现"]},
        {"name": "light_leak", "description": "图片从电影感的漏光和光晕中显现。", "examples": ["漏光中出现", "光晕揭示画面", "光线扫过后显现"]},
        {"name": "stretch_reveal", "description": "图片通过拉伸进入画面，动画结束后恢复静止。", "examples": ["丝滑拉伸进入", "图片展开出现", "柔性拉开入场"]},
        {"name": "drop_reveal_elastic", "description": "图片从指定方向落入画面，并以弹性方式停稳。", "examples": ["从上方弹性落下", "图片掉入画面", "橡胶般落地"]},
        {"name": "particle_flip_reveal", "description": "图片伴随粒子帷幕和翻转效果组装显现。", "examples": ["粒子翻转进入", "碎片汇聚成画面", "粒子组装出现"]},
        {"name": "creative_reveal", "description": "图片通过柔和遮罩、透明度或轻微位移完成受控揭示。", "examples": ["遮罩展开", "柔和显现", "从中心揭示"]},
    ],
    "transition": [
        {"name": "glass_shatter_transition", "description": "真实玻璃破碎、裂纹扩散、碎片飞散的视觉转场。", "examples": ["玻璃破碎", "裂纹扩散", "碎片炸开"]},
        {"name": "shake_transition", "description": "快速震动、冲击感、力量感转场。", "examples": ["强烈震动", "冲击切换", "镜头震颤"]},
        {"name": "card_flip_transition", "description": "三维页面翻转、卡片旋转切换。", "examples": ["页面翻转", "卡片翻面", "3D翻转"]},
        {"name": "gaussian_blur_transition", "description": "失焦、柔焦、梦境、回忆感转场。", "examples": ["逐渐模糊", "失焦进入", "梦幻过渡"]},
        {"name": "directional_blur_transition", "description": "高速方向运动造成的速度模糊转场。", "examples": ["横向速度切换", "快速扫过", "极速移动"]},
        {"name": "pixel_blur_transition", "description": "数字化像素模糊效果。", "examples": ["数字化消散", "像素化过渡"]},
        {"name": "bokeh_blur_transition", "description": "电影光斑、柔和散景效果。", "examples": ["光斑散开", "梦幻光晕"]},
        {"name": "water_ripple_transition", "description": "水波、液体、波纹扩散。", "examples": ["水面波纹", "涟漪扩散"]},
    ],
}


def director_capability_guidance() -> str:
    return json.dumps(DIRECTOR_VISUAL_CAPABILITIES, ensure_ascii=False, sort_keys=True)


_ADAPTATION_RULES = (
    (re.compile(r"粒子|particle|爆炸", re.IGNORECASE), "强烈冲击、碎裂感、震动效果", "transition"),
    (re.compile(r"拉伸切换|stretch_transition", re.IGNORECASE), "图片以拉伸方式进入下一镜头", "entrance"),
    (re.compile(r"电影感展示|cinematic", re.IGNORECASE), "保持电影感构图与节奏，不额外添加特殊效果", "none"),
)


def log_intent_adaptation(requested_intent: str, adapted_visual_language: str | None = None, selected_capability_family: str | None = None) -> None:
    for pattern, adapted, family in _ADAPTATION_RULES:
        if pattern.search(requested_intent):
            logger.debug("Director intent adaptation | Requested intent: %s | Adapted visual language: %s | Selected capability family: %s", requested_intent, adapted_visual_language or adapted, selected_capability_family or family)
            return
