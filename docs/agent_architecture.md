# Agent 架构说明

## 当前流程

```text
VideoState
   |
   v
Vision Agent       本地分析图片尺寸、平均色、复杂度
   |
   v
Director Agent     LLM 或规则生成 DirectorPlan
   |
   v
Remotion Agent     Skill 约束 + AnimationPlan 映射
   |
   v
Render Agent       Storyboard、Timeline、音频适配和渲染
   |
   v
END -> MP4
```

LangGraph State 使用 `VideoProject`、`ImageAnalysis`、`BeatAnalysis`、`DirectorPlan`、`AnimationPlan`、Storyboard、RemotionAdvice、Render Plan 和错误列表在节点间传递。

## Vision Agent

V1 不调用视觉大模型。它使用 Pillow 读取尺寸、宽高比、平均背景色和基础信息密度，为 Director 提供可复现的素材分析。

## Director Agent

Director Agent 负责图片停留时间、转场、节奏、情绪和动画意图。输出必须是 `DirectorPlan`，包含一个与图片一一对应的 `timeline`。默认 `motion=static`，不直接生成 TSX、React、CSS 或 ffmpeg。

## Remotion Creative Agent

Creative Agent 不生成任意源码，而是将 `animation_intent` 映射为 `AnimationPlan`。它读取 `.agents/skills/` 中的官方 Remotion 文档，确认 API 和项目约束后选择已注册效果。当前映射：

```text
3d_card_flip -> CardFlipReveal
camera_push  -> CameraPush
glitch       -> GlitchReveal
light_leak   -> LightLeak
```

不支持的意图保留原始 JSON，并降级为 `FadeFallback`。

## Render Agent

Render Agent 将 DirectorPlan 转为 Storyboard，再编译绝对时间轴。它把 AnimationPlan 绑定到 `TimelineItem.animation`，生成 `render_data.json`，按最终 Timeline 时长调用 BGM adapter，最后交给本地 Remotion Renderer。

## Director Workspace

交互 CLI 使用 `ProjectSession` 保存绝对资源路径、当前计划、Storyboard、分析结果、对话历史和预览/正式视频路径。`plan` 生成计划；自然语言输入修改当前计划；`preview` 和 `render` 使用同一份当前计划；`quit` 自动保存。

## 未来 Agent

```text
Vision Agent   -> 图片理解
Music Agent    -> 音乐段落和能量
Director Agent -> 镜头和节奏
Creative Agent -> 动画实现计划
Render Agent   -> 本地渲染
Subtitle Agent -> 未来字幕规划
```

未来 Agent 仍只能通过结构化 Schema 协作，不能让 LLM 直接控制 Remotion 源码、ffmpeg 或文件系统。
