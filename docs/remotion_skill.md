# Remotion Skill 使用说明

## 1. Skill 的作用

项目通过 `remotion-dev/skills` 安装官方 Remotion 知识文档，当前位于 `.agents/skills/`。Creative Agent 会读取以下技能文档，用于核对 API、Composition、动画、转场和渲染建议：

- `remotion-best-practices`、`remotion-docs`、`remotion-markup`、`remotion-render`：Remotion 官方开发知识。
- `video-assistant-visual-events`：项目自定义的视觉事件协议（阶段、组合与安全规则）。
- `remotion-motion-design`、`stretch-motion-design`、`elastic-blur-motion-design`、`blur-transition-design`、`zoom-motion-design`：入场动画与转场的专项设计指导。

Skill 是开发期知识资源，不是运行时渲染引擎，也不会替代 Remotion CLI。

## 2. 使用流程

```text
DirectorPlan（creative_intent / transition_intent）
          -> Creative Agent
          -> 读取 Skill 文档
          -> RemotionCreativePlan（VisualEvent）
          -> EffectRegistry / TransitionEffectRegistry
          -> Remotion Effect
          -> Render Agent
```

Creative Agent 只输出实现中立的视觉事件计划，不让 LLM 直接生成 TSX。未知或校验失败的事件被丢弃并记录日志；LLM 不可用时仅保留入场 `creative_reveal` 降级，不生成创意转场。

## 3. 当前开发规则

- 使用当前项目已安装并通过 TypeScript 检查的 Remotion API。
- 动画优先使用 `useCurrentFrame`、`interpolate`、`spring` 和 `Easing`。
- 场景由 `Composition`、`Sequence`、`TransitionSeries` 组合。
- 转场统一走 Transition Registry（基线 `TransitionFactory` + 创意 `TransitionEffectRenderer`）；动画统一走 Effect Registry。
- 图片必须 contain、等比例、完整显示；默认 `motion=static`。
- 禁止 `object-fit: cover`、crop、`scaleX`、`scaleY` 和永久放大。
- 效果结束后应恢复原始场景，不留下持续的 transform、filter 或遮罩（入场结束须为 scale 1、rotate 0、translate 0、opacity 1、blur 0）。

## 4. 当前效果实现

效果代码位于 `remotion/src/effects/`，通过 `remotion/src/effects/index.tsx` 的 `EffectRegistry` 注册：

- `CardFlipReveal`：CSS `rotateY` 卡片翻转入场。
- `CameraPush`：短暂平移叠层，底层保持完整图片；仅显式镜头语言时保留。
- `GlitchReveal`：确定性的 RGB 偏移和切片。
- `LightLeak`：只绘制光漏 overlay。
- `StretchReveal`：丝滑拉伸入场。
- `ElasticBlurReveal`：加权弹性拉伸 + 轻微镜头模糊入场（18-36 帧，入场专用）。
- `DropRevealElastic`：从指定方向落下并弹性回弹入场。
- `ParticleFlipReveal`：粒子面纱翻转入场。
- `CreativeReveal`：安全蒙版淡入（默认降级与未知效果的安全预览）。

效果组件不得自行改变 ImageFrame 的 contain 几何。

## 5. 创意转场实现

场景转场统一使用 `template_transition` 基础设施，并由 Python 与 Remotion 两端的模板注册表共同注册。当前唯一正式模板是 `qwen3_8`，Agent 不得选择其他模板。

`TransitionEffectRenderer` 只负责渲染已注册的模板转场。旧的 `TransitionFactory` 和 `fade`、`crossfade`、`wipe`、`slide`、`push`、`whip` 等场景转场已删除；没有 qwen effect 时直接硬切。

## 6. 代码边界与验证

Skill 参考产生的入场动画只能进入 `remotion/src/effects/`。场景转场只能进入 `remotion/src/transitions/templates/`，并同步更新 Registry、Schema 和测试。未经设计变更，不要改写 `ImageFrame`、Timeline 计算、Media Server 权限或 Composition 的整体结构。

验证命令：

```bash
cd remotion
pnpm exec tsc --noEmit
pnpm run build
pnpm exec remotion bundle src/index.ts /tmp/video-assistant-remotion-bundle
```

实际效果仍需使用本地素材渲染，并用 `ffprobe` 检查视频尺寸、帧率、音频流和时长。
