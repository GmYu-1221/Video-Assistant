# Agent 架构说明

## 当前 Agent

### Vision Agent

当前实现使用 Pillow 做本地规则分析，包括图片尺寸、宽高比、背景平均色和边缘复杂度。它不调用视觉大模型。

### Director Agent

Director Agent 接收 `ImageAsset`、`BeatAnalysis` 和风格，生成 `DirectorPlan`。它决定图片停留、转场类型、转场强度、情绪和导演理由。LLM 输出必须是 JSON，并经过 Pydantic、转场注册表和安全策略校验。

### Remotion Agent

Remotion Agent 读取 `.agents/skills/` 中安装的 Remotion Skill 文档，检查 Storyboard 是否符合 contain、static motion、合法动画 API 和 Transition Registry 约束。它输出建议，不生成任意 TSX。

### Render Agent

Render Agent 将 Storyboard 编译为 Timeline、生成 `render_data.json`，适配 BGM，并调用现有 Remotion Renderer。Media Server 生命周期由 Renderer 管理。

## LangGraph 流程

```text
START
  │
  v
Vision Agent（本地图片分析）
  │ image_analysis
  v
Director Agent（LLM 或规则回退）
  │ DirectorPlan / Storyboard
  v
Remotion Agent（Skill 约束建议）
  │ RemotionAdvice
  v
Render Agent（Timeline + Renderer）
  │
  v
END -> final.mp4
```

`VideoState` 在节点间携带 `VideoProject`、图片分析、`DirectorPlan`、Storyboard、Remotion 建议、Render Plan 和错误列表。

## 交互式 Director Chat

`uv run python -m content_creator.director_chat` 读取现有项目的 `render_data.json` 和 `director_plan.json`。用户输入被转换为结构化 `DirectorIntent`，只对当前计划做增量修改，并保存会话历史。Chat Agent 不修改 Remotion 源码，也不生成实现代码。

## 未来 Agent

```text
Vision Agent      -> 图片理解
Music Agent       -> 音乐段落和能量
Director Agent    -> 镜头、停留和转场决策
Remotion Agent    -> 动画实现建议
Render Agent      -> 最终本地渲染
```

当前 Vision 和 Music 已有本地规则能力；独立的未来 Agent 接口尚不代表已经接入云端模型。
