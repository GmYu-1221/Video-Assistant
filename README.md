# Video Assistant

将 1～3 篇公开文章融合为一条中文竖屏短视频。内容决策由 LangGraph 多 Agent 工作流完成，视觉产物是模型生成的完整 HTML/CSS/GSAP 文档；Chromium 按帧截图后直接通过内存管道交给 FFmpeg。

## 生产流程

```text
URLs → Source → Editorial → Director → Timing Compiler → Copy Fitting → Presentation Compiler ↔ Director Review → Animation
     → AnimationArtifact → HTML Validator → Chromium → FFmpeg + BGM → final.mp4
```

Chromium 和 FFmpeg 是 Graph 外的确定性执行层。项目没有固定动画模板，也不会在模型失败后生成降级 HTML。

## 启动

```bash
make install
make browser
make web
```

打开 `http://127.0.0.1:8000`，输入一至三个 URL。模型配置从仓库 `.env` 读取；至少配置 `OPENAI_API_KEY` 和 `LLM_MODEL`。可分别设置：

```text
ARTICLE_MODEL
ASSET_MODEL
EDITORIAL_MODEL
COPY_FITTING_MODEL
DIRECTOR_MODEL
ANIMATION_MODEL
```

各专用模型未设置时使用 `LLM_MODEL`；Provider 为 Mock 或模型调用失败时，任务直接进入 `failed`。

更多信息见 [架构](docs/architecture.md) 和 [使用说明](docs/usage.md)。
