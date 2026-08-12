# Remotion Skill 使用说明

## 1. 为什么引入 Skill

Remotion Skill 是安装在项目 `.agents/skills/` 下的官方知识文档集合。它为开发和 Agent 提供 Remotion API、Composition、动画、转场和渲染实践参考，减少凭空猜测 API 导致的实现错误。

Skill 不是运行时视频引擎，也不会替代 Remotion CLI。真正的视频渲染仍由 `remotion/` 工程和本地 `pnpm` 命令完成。

## 2. Agent 如何使用

Remotion Agent 在 LangGraph 中读取 Skill 文档，根据已经校验的 Storyboard 输出 `RemotionAdvice`，例如使用哪个 Composition、图片适配方式、动画 API 和 Transition Registry。

```text
Storyboard
   -> Remotion Agent 读取 Skill
   -> RemotionAdvice
   -> Render Agent
   -> 现有 Remotion 工程
```

当前 Agent 不生成随机 TSX，不调用 ffmpeg，也不直接改写 Remotion 项目。

## 3. Skill 覆盖的开发规则

- 使用 Remotion 官方组件和当前版本真实存在的 API。
- 动画优先使用 `interpolate`、`spring`、`Easing`。
- 场景使用 `Sequence` / `TransitionSeries` 组织。
- 转场统一通过 Transition Registry。
- 图片使用 `contain`，保持原始宽高比。
- 默认 `motion=static`，避免持续 zoom / pan。
- 渲染时使用 `calculateMetadata` 和实际 Timeline 末帧决定时长。

## 4. 图片与渲染安全规则

禁止：

- `object-fit: cover`
- crop / center-crop
- `scaleX` / `scaleY`
- 直接生成整个 Remotion 项目
- 通过动画破坏图片完整显示

Skill 的示例或建议必须经过当前项目的 TypeScript 检查、图片安全规则和实际渲染验证。

## 5. 代码修改边界

未来由 Skill 或 Creative Agent 生成的效果组件，代码只能进入：

```text
remotion/src/effects/
```

并应通过现有 Transition Registry 接入。未经明确设计评审，不应随意修改 `Composition.tsx`、Python Timeline Schema、图片 contain 逻辑或 Media Server 权限边界。

如果新增效果需要改动 Registry 或数据 Schema，应同时补充 Python/TypeScript 测试；不能把文档示例直接复制为生产代码。
