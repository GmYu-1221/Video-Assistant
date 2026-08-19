# 转场模板开发说明

当前生产环境启用两个转场模板：`qwen3_8` 和 `zoom_whip_v2`。前者是克制的模糊上浮，后者是快速横向甩镜。

## 当前规则

- URL 视频首图没有 incoming transition；每个相邻图片边界都必须使用一个完整注册转场，末图没有 outgoing transition。
- Agent 只能输出 `template_transition` 和当前启用的 `qwen3_8` / `zoom_whip_v2`。
- Agent 未返回合法模板、参数非法或模型不可用时，确定性回退到 `qwen3_8`。
- 镜头时长必须满足所选模板最小时长；不能满足时明确失败，不恢复旧转场。
- Agent 不得输出组件、源码、路径、导入、CSS 或其他 Remotion 实现细节。

## qwen3_8 参数

Python 和 Remotion 两端必须使用同一份参数契约：

- `blur_strength`：初始模糊强度，默认 `0.8`。
- `float_distance`：上浮距离，默认 `0.55`。
- `recovery_speed`：恢复速度，默认 `0.7`。
- `opacity_start`：入场初始不透明度，默认 `0.88`。
- 时长范围：`12–45` 帧，默认 `27` 帧。

模板实现位于 `remotion/src/transitions/templates/`，注册信息位于 Python 的 `TRANSITION_TEMPLATE_REGISTRY` 和 Remotion 的 `TemplatePresentationRegistry`。

## zoom_whip_v2 参数

- `zoom`：最大缩放，默认 `1.08`，范围 `1.0–1.2`。
- `distance`：横向甩镜距离百分比，默认 `12`，范围 `3–30`。
- `blur`：最大模糊像素，默认 `10`，范围 `0–24`。
- 时长范围：`9–36` 帧，默认 `20` 帧（约 650ms）。

## 添加新模板

在用户明确提供并验收新的模板前，不要添加其他转场。添加时必须：

1. 在 `remotion/src/transitions/templates/` 创建模板呈现组件。
2. 在 Python 和 Remotion 两端注册相同的模板 ID。
3. 为参数、时长和 JSON 安全性增加 schema 校验。
4. 增加 Agent 非法输出、渲染、关键帧和视觉回归测试。
5. 运行 Python 测试和 `cd remotion && pnpm exec tsc --noEmit`。
