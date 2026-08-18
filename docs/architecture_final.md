# Video-Assistant 架构

## 运行时流程

```text
用户请求
  -> Director Agent
  -> DirectorPlan（creative_intent、transition_intent）
  -> 一个 Remotion Creative Agent
     -> RemotionCreativePlan（VisualEvent 列表）
  -> render_data.json
  -> Remotion Renderer
     -> EffectRenderer
     -> TransitionEffectRenderer（qwen3_8）或硬切
  -> MP4
```

Director 负责解释意图：它在 `creative_intent` 中描述场景内的运动，在 `transition_intent` 中描述场景边界的转场。它不选择 Remotion 组件名、注册效果标识符或 TSX 参数。

只有一个 Remotion Creative Agent，而不是独立的动画或转场 Agent。它每次计划运行调用一次 `get_agent_provider("remotion")`，同一 Provider 用于所有输出。它读取 `.agents/skills/` 下安装的项目技能（`video-assistant-visual-events`、`remotion-motion-design`、`stretch-motion-design`、`elastic-blur-motion-design`、`blur-transition-design`、`zoom-motion-design`、`remotion-best-practices`、`remotion-docs`、`remotion-markup`、`remotion-render`），并在提示词中收到已注册能力清单。

## 计划契约

入场/场景动画以视觉事件形式挂到场景上：

```json
{"type":"particle_flip_reveal","phase":"entrance","start_frame":0,"duration_frames":24,"params":{"particle_density":240,"rotation_axis":"Y"}}
```

创意转场也以视觉事件形式挂到出场景上，但只有双端注册表存在启用模板时才会生成。

`render_data.json` 是渲染器契约。一个 `timeline` 项可以同时包含动画与转场事件。

## 渲染器优先级

`Composition.tsx` 在每个非最终场景边界应用以下规则：

1. 当存在创意转场事件时，调用 `TransitionEffectRenderer`。
2. 没有 qwen 转场事件时直接硬切，不调用任何旧转场工厂。

这样可以确保旧的 `fade`、`crossfade`、`wipe`、`slide` 等转场不会重新进入新成片。只有注册的 `qwen3_8` 才能执行场景转场。

`TransitionEffectRenderer` 与场景 `EffectRenderer` 相互独立。前者只识别 `template_transition` 基础类型，并根据 `template_id` 查询只包含 `qwen3_8` 的 `TemplatePresentationRegistry`。

## 添加一个场景动画

1. 在 `remotion/src/effects/` 下用帧驱动的 Remotion API 实现 TSX 效果。
2. 在场景 `EffectRegistry` 中注册。
3. 在 Python 动画 Schema 与 Remotion Creative Agent 提示词中加入枚举值与能力元数据。
4. 校验参数，并添加 LLM 到 `render_data.json` 的测试。

## 添加一个转场效果

1. 在 `remotion/src/transitions/templates/` 下实现 Remotion 转场呈现。
2. 添加类型化的转场事件条目，并在 `TransitionEffectRenderer.tsx` 的 `TransitionEffectRegistry` 中注册。
3. 在 `transition_effect_plan.py` 与 `remotion_agent.py` 中添加对应的 Python 枚举与能力元数据。
4. 添加参数校验、LLM 计划、渲染数据和渲染器分发测试。

不要为一个效果新增 LLM Agent。扩展现有 Remotion Creative Agent 及其能力注册表即可。

## 开发者注意事项

- `TransitionConfig` 仍是安全的基线时间轴机制，不是 Director 的创意决策格式。
- LLM 选择了未注册类型属于校验错误。非法 JSON、Provider 不可用和网络失败使用记录日志的安全降级。
- CLI 的 `show` 输出区分 `Transition`（基线）与 `Creative Transition`（导演意图），渲染前不会混淆两者。
- 入场事件结束后图片必须保持静止（scale 1、rotate 0、translate 0、opacity 1、blur 0）；转场事件拥有目标素材的揭示，目标场景不再叠加入场事件。
