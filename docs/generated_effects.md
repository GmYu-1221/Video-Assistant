# 生成效果（Generated Effects）

创意模式的入场效果是依据结构化创意意图生成、注册在 `remotion/src/effects/` 下的实现计划。以下效果由 Remotion Creative Agent 从能力注册表中选择，经 Pydantic 参数校验后写入 `render_data.json`。

## stretch_reveal（丝滑拉伸入场）

- 导演描述：图片从指定方向拉伸进入。
- 文件：`remotion/src/effects/StretchReveal.tsx`
- 注册：`remotion/src/effects/index.tsx`（`EffectRegistry`）
- API：`useCurrentFrame`、`useVideoConfig`、`spring`、`interpolate`
- 参数：`strength`（强度）、`blurPx`（模糊像素）、`duration_frames`
- 安全：入场结束后移除 transform 与 filter，被包裹的 `ImageFrame` 保持 contain。

## elastic_blur_reveal（弹性模糊入场）

- 导演描述：带权重的水平拉伸、轻微垂直压缩与镜头模糊，弹性回弹后完全静止。
- 文件：`remotion/src/effects/ElasticBlurReveal.tsx`
- 注册：`remotion/src/effects/index.tsx`（`EffectRegistry`）
- API：`useCurrentFrame`、`interpolate`、`spring`、`Easing`
- 参数：`intensity`（0-1）、`blur_px`（0-24）、`opacity`（0-1）
- 约束：仅入场阶段，时长 18-36 帧，结束必须回到 scale 1、blur 0、opacity 1；不得用作转场。

## drop_reveal_elastic（弹性落下入场）

- 导演描述：图片从指定方向落下并弹性回弹。
- 文件：`remotion/src/effects/DropRevealElastic.tsx`
- 注册：`remotion/src/effects/index.tsx`（`EffectRegistry`）
- API：`useCurrentFrame`、`interpolate`、`spring`
- 参数：`direction`（`top` / `bottom` / `left` / `right`）
- 安全：入场结束后回到原始静止场景。

## particle_flip_reveal（粒子翻转入场）

- 导演描述：图片在粒子面纱中翻转入场。
- 文件：`remotion/src/effects/ParticleFlipReveal.tsx`
- 注册：`remotion/src/effects/index.tsx`（`EffectRegistry`）
- API：`useCurrentFrame`、`interpolate`
- 参数：`particle_density`（24-500）、`rotation_axis`（`X` / `Y`）、`motion_blur`、`perspective`（100-2000）
- 安全：粒子层为叠加的径向渐变遮罩，不改变图片 contain 几何。

## creative_reveal（安全蒙版淡入）

- 导演描述：带不透明度和可选垂直运动的蒙版淡入。
- 文件：`remotion/src/effects/CreativeReveal.tsx`
- 注册：`remotion/src/effects/index.tsx`（`EffectRegistry`）
- API：`useCurrentFrame`、`interpolate`
- 参数：`direction`（`up` / `center`）、`energy`（0-1）、`blurPx`（0-40）、`mask`（布尔）
- 角色：LLM 不可用或输出校验失败时的默认入场降级，也是未知效果的安全预览组件。

## 生成与降级策略

效果由 `create_remotion_creative_plan` 统一生成：LLM 从能力注册表选择注册类型并给出参数，本地完成阶段、时长、参数范围校验，非法事件被丢弃。LLM 不可用或全部事件非法时，入场可使用 `creative_reveal`；创意转场直接省略。运行时不会执行任意的源码生成。
