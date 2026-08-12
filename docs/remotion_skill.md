# Remotion Skill 使用说明

## 1. Skill 的作用

项目通过 `remotion-dev/skills` 安装官方 Remotion 知识文档，当前位于 `.agents/skills/`。Creative Agent 会读取可用的 `remotion-best-practices`、`remotion-docs`、`remotion-markup` 和 `remotion-render` 文档，用于核对 API、Composition、动画、转场和渲染建议。

Skill 是开发期知识资源，不是运行时渲染引擎，也不会替代 Remotion CLI。

## 2. 使用流程

```text
DirectorPlan.animation_intent
          -> Creative Agent
          -> 读取 Skill 文档
          -> AnimationPlan
          -> EffectRegistry
          -> Remotion Effect
          -> Render Agent
```

Creative Agent 只输出实现中立的 `AnimationPlan`，不让 LLM 直接生成 TSX。未知或暂未实现的意图保留在导演方案中，并使用安全 fallback。

## 3. 当前开发规则

- 使用当前项目已安装并通过 TypeScript 检查的 Remotion API。
- 动画优先使用 `useCurrentFrame`、`interpolate`、`spring` 和 `Easing`。
- 场景由 `Composition`、`Sequence`、`TransitionSeries` 组合。
- 转场统一走 Transition Registry；动画统一走 Effect Registry。
- 图片必须 contain、等比例、完整显示；默认 `motion=static`。
- 禁止 `object-fit: cover`、crop、`scaleX`、`scaleY` 和永久放大。
- 效果结束后应恢复原始场景，不留下持续的 transform、filter 或遮罩。

## 4. 当前效果实现

效果代码位于 `remotion/src/effects/`：

- `CardFlipReveal`：CSS `rotateY` 卡片翻转。
- `CameraPush`：短暂平移叠层，底层保持完整图片。
- `GlitchReveal`：确定性的 RGB 偏移和切片。
- `LightLeak`：只绘制光漏 overlay。

通过 `remotion/src/effects/index.tsx` 的 `EffectRegistry` 注册。效果组件不得自行改变 ImageFrame 的 contain 几何。

## 5. 代码边界与验证

Skill 参考产生的效果实现只能进入 `remotion/src/effects/`，并应同步更新 Registry、Schema 和测试。未经设计变更，不要改写 `ImageFrame`、Timeline 计算、Media Server 权限或 Composition 的整体结构。

验证命令：

```bash
cd remotion
pnpm exec tsc --noEmit
pnpm run build
pnpm exec remotion bundle src/index.ts /tmp/video-assistant-remotion-bundle
```

实际效果仍需使用本地素材渲染，并用 `ffprobe` 检查视频尺寸、帧率、音频流和时长。
