# 转场模板开发说明

当前生产环境只启用一个转场模板：`qwen3_8`。它让下一张图片以模糊、略微下移的状态进入，并在 27 帧内平滑恢复清晰和静止位置。

## 当前规则

- `continuous`：保持当前画面，不执行场景转场。
- `accent`：只做场景内局部强调，不执行完整转场。
- `scene_cut`：统一使用 `qwen3_8`。
- 镜头时长不足模板最小 12 帧时使用硬切，不回退到其他旧转场。
- Agent 只能输出 `template_transition` 和已注册的 `template_id`，目前唯一合法值是 `qwen3_8`。
- Agent 不得输出组件、源码、路径、导入、CSS 或其他 Remotion 实现细节。

## qwen3_8 参数

Python 和 Remotion 两端必须使用同一份参数契约：

- `blur_strength`：初始模糊强度，默认 `0.8`。
- `float_distance`：上浮距离，默认 `0.55`。
- `recovery_speed`：恢复速度，默认 `0.7`。
- `opacity_start`：入场初始不透明度，默认 `0.88`。
- 时长范围：`12–45` 帧，默认 `27` 帧。

模板实现位于 `remotion/src/transitions/templates/`，注册信息位于 Python 的 `TRANSITION_TEMPLATE_REGISTRY` 和 Remotion 的 `TemplatePresentationRegistry`。

## 添加新模板

在用户明确提供并验收新的模板前，不要添加其他转场。添加时必须：

1. 在 `remotion/src/transitions/templates/` 创建模板呈现组件。
2. 在 Python 和 Remotion 两端注册相同的模板 ID。
3. 为参数、时长和 JSON 安全性增加 schema 校验。
4. 增加 Agent 非法输出、渲染、关键帧和视觉回归测试。
5. 运行 Python 测试和 `cd remotion && pnpm exec tsc --noEmit`。
