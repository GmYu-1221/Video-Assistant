---
name: blur-transition-design
description: >
  Guide Remotion Creative Agent to choose cinematic blur based transitions.
  Use when creating soft, dreamy, focus, mist, water ripple or digital blur transitions.
---

# Blur Transition Design

## Purpose

Blur transitions simulate:

- focus change
- dream state
- memory
- atmosphere
- smooth scene replacement

## Effect Selection

### gaussian_blur_transition

Use for:

- 逐渐失焦
- 梦幻
- 回忆
- 柔和过渡

Avoid:

- fast action

### directional_blur_transition

Use for:

- 快速切换
- 速度感
- 横向移动

Examples:

- 横向模糊切换
- 速度拉伸

### pixel_blur_transition

Use for:

- digital
- futuristic
- UI
- technology

### bokeh_blur_transition

Use for:

- cinematic light
- romance
- dreamy atmosphere

### water_ripple_transition

Use for:

- water
- reflection
- liquid
- ripple

## Director Intent Mapping

"逐渐模糊"
-> gaussian_blur_transition

"失焦进入"
-> gaussian_blur_transition

"像水面一样扩散"
-> water_ripple_transition

"横向快速模糊"
-> directional_blur_transition

"数字化模糊"
-> pixel_blur_transition

"光斑散开"
-> bokeh_blur_transition

## Rules

- Do not generate blur transition from "cinematic" alone.
- Blur is a transition, not an entrance animation.
- Do not combine blur transition with competing reveal effects.
- Transition owns target image reveal.
- For an unspecified strong transition, prefer restrained `shake_transition`;
  do not substitute glass shatter without explicit glass or fragment language.
