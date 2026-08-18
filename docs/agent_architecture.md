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
Remotion Agent     Skill 约束 + RemotionCreativePlan（VisualEvent）映射
   |
   v
Render Agent       Storyboard、Timeline、音频适配和渲染
   |
   v
END -> MP4
```

LangGraph State 使用 `VideoProject`、`ImageAnalysis`、`BeatAnalysis`、`DirectorPlan`、`RemotionCreativePlan`、Storyboard、RemotionAdvice、Render Plan 和错误列表在节点间传递。

Web 文章转视频模式还使用 Article/Asset Agent（正文与配图提取）、Layout Director 与 Visual Critic（竖屏排版设计与审查），但都不直接接触渲染代码。

## Vision Agent

V1 不调用视觉大模型。它使用 Pillow 读取尺寸、宽高比、平均背景色和基础信息密度，为 Director 提供可复现的素材分析。

## Director Agent

Director Agent 负责图片停留时间、转场、节奏、情绪和创意意图。输出必须是 `DirectorPlan`，包含一个与图片一一对应的 `timeline`。默认 `motion=static`，不直接生成 TSX、React、CSS 或 ffmpeg。

交互式 Workspace 的自然语言修改走 `DirectorPlanPatch`：LLM 只返回针对指定场景的小型补丁，本地合并后重新校验，避免整体重写方案。

## Remotion Creative Agent

Creative Agent 不生成任意源码，而是把导演的创意意图映射为注册的视觉事件。它读取 `.agents/skills/` 中的项目技能文档（`video-assistant-visual-events`、`remotion-motion-design`、`stretch-motion-design`、`elastic-blur-motion-design`、`blur-transition-design`、`zoom-motion-design` 以及 `remotion-best-practices`、`remotion-docs`、`remotion-markup`、`remotion-render`），确认 API 和项目约束后选择已注册效果。

入场/场景动画（9 个）：

```text
card_flip_reveal   -> CardFlipReveal
camera_push        -> CameraPush
glitch_reveal      -> GlitchReveal
light_leak         -> LightLeak
stretch_reveal     -> StretchReveal
elastic_blur_reveal-> ElasticBlurReveal
drop_reveal_elastic-> DropRevealElastic
particle_flip_reveal-> ParticleFlipReveal
creative_reveal    -> CreativeReveal（默认降级）
```

创意转场统一通过 `template_transition` 扩展入口注册。当前正式模板数量为 0。不支持的意图保留在导演方案中；LLM 不可用或输出校验失败时，入场降级为 `creative_reveal`，不生成创意转场。

## Render Agent

Render Agent 将 DirectorPlan 转为 Storyboard，再编译绝对时间轴。它把视觉事件绑定到 TimelineItem 的动画与转场字段，生成 `render_data.json`，按最终 Timeline 时长调用 BGM adapter，最后交给本地 Remotion Renderer。

## Director Workspace

交互 CLI 使用 `ProjectSession` 保存绝对资源路径、当前计划、Storyboard、分析结果、对话历史和预览/正式视频路径。`plan` 生成计划；自然语言输入通过 `DirectorPlanPatch` 修改当前计划；`preview` 和 `render` 使用同一份当前计划；`quit` 自动保存。

## Web 文章转视频

`content_creator.web` 提供本地 Web 服务：提交文章 URL 后，Article/Asset Agent 提取正文与图片，BGM 目录选曲，生成竖屏 1080x1920 视频。禁止抓取的网站可把 bookmarklet 拖到书签栏，在文章页点击后把 DOM 回传本地服务。视频支持版本化反馈：负反馈触发 Layout Director 重新设计字体与字幕（`revise_typography`），生成 `vNNN` 新版本；用户偏好记录在 `output/preferences/`。

## 未来 Agent

```text
Vision Agent   -> 图片理解
Music Agent    -> 音乐段落和能量
Director Agent -> 镜头和节奏
Creative Agent -> 动画实现计划
Render Agent   -> 本地渲染
Subtitle Agent -> 未来字幕规划
```

Layout Director 与 Visual Critic 已承担部分排版/字幕职能，独立的 Subtitle Agent（如歌词/对白字幕）仍属未来规划。未来 Agent 仍只能通过结构化 Schema 协作，不能让 LLM 直接控制 Remotion 源码、ffmpeg 或文件系统。
