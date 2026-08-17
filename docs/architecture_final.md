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
     -> TransitionEffectRenderer 或基线 TransitionFactory
  -> MP4
```

Director 负责解释意图：它在 `creative_intent` 中描述场景内的运动，在 `transition_intent` 中描述场景边界的转场。它不选择 Remotion 组件名、注册效果标识符或 TSX 参数。

只有一个 Remotion Creative Agent，而不是独立的动画或转场 Agent。它每次计划运行调用一次 `get_agent_provider("remotion")`，同一 Provider 用于所有输出。它读取 `.agents/skills/` 下安装的项目技能（`video-assistant-visual-events`、`remotion-motion-design`、`stretch-motion-design`、`elastic-blur-motion-design`、`blur-transition-design`、`zoom-motion-design`、`remotion-best-practices`、`remotion-docs`、`remotion-markup`、`remotion-render`），并在提示词中收到已注册能力清单。

## 计划契约

入场/场景动画以视觉事件形式挂到场景上：

```json
{"type":"particle_flip_reveal","phase":"entrance","start_frame":0,"duration_frames":24,"params":{"particle_density":240,"rotation_axis":"Y"}}
```

创意转场也以视觉事件形式挂到出场景上：

```json
{"type":"glass_shatter_transition","phase":"transition","start_frame":30,"duration_frames":45,"source_asset_id":"image-001","target_asset_id":"image-002","params":{"fragment_count":48,"impact_origin":"center","motion_blur":true}}
```

`render_data.json` 是渲染器契约。一个 `timeline` 项可以同时包含动画与转场事件。

## 渲染器优先级

`Composition.tsx` 在每个非最终场景边界应用以下规则：

1. 当存在创意转场事件时，调用 `TransitionEffectRenderer`。
2. 否则调用基线 `TransitionFactory` 处理 `timeline.transition`。

这样 `fade`、`crossfade`、`wipe`、`slide` 等所有既有基线转场保持兼容，AI 选择的创意转场也不会静默回落到基线转场。

`TransitionEffectRenderer` 与场景 `EffectRenderer` 相互独立，通过 `TransitionEffectRegistry` 分发。注册表当前包含：`card_flip_transition`（卡片翻转转场）、`glass_shatter_transition`（玻璃破碎，出场景被裁剪为碎片图层，带不透明度分解、位移、旋转、可选模糊与入场景揭示）、`shake_transition`（抖动冲击）、`gaussian_blur_transition` / `directional_blur_transition` / `pixel_blur_transition` / `bokeh_blur_transition` / `water_ripple_transition`（五类模糊转场）以及 `zoom_through_transition`（放大穿过转场）。

## 添加一个场景动画

1. 在 `remotion/src/effects/` 下用帧驱动的 Remotion API 实现 TSX 效果。
2. 在场景 `EffectRegistry` 中注册。
3. 在 Python 动画 Schema 与 Remotion Creative Agent 提示词中加入枚举值与能力元数据。
4. 校验参数，并添加 LLM 到 `render_data.json` 的测试。

## 添加一个转场效果

1. 在 `remotion/src/transitions/presentations/` 下实现 Remotion 转场呈现。
2. 添加类型化的转场事件条目，并在 `TransitionEffectRenderer.tsx` 的 `TransitionEffectRegistry` 中注册。
3. 在 `transition_effect_plan.py` 与 `remotion_agent.py` 中添加对应的 Python 枚举与能力元数据。
4. 添加参数校验、LLM 计划、渲染数据和渲染器分发测试。

不要为一个效果新增 LLM Agent。扩展现有 Remotion Creative Agent 及其能力注册表即可。

## 开发者注意事项

- `TransitionConfig` 仍是安全的基线时间轴机制，不是 Director 的创意决策格式。
- LLM 选择了未注册类型属于校验错误。非法 JSON、Provider 不可用和网络失败使用记录日志的安全降级。
- CLI 的 `show` 输出区分 `Transition`（基线）与 `Creative Transition`（导演意图），渲染前不会混淆两者。
- 入场事件结束后图片必须保持静止（scale 1、rotate 0、translate 0、opacity 1、blur 0）；转场事件拥有目标素材的揭示，目标场景不再叠加入场事件。
