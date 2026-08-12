# Video-Assistant 使用手册

## 1. 项目介绍

Video-Assistant 是一个本地图片转视频工具。它使用 Pillow 处理图片、使用 librosa 分析 BGM 节拍，由规则管线或 Director Agent 生成导演方案，再由 Remotion 输出 MP4。

```text
图片素材 + 本地 BGM
        -> 图片/节拍分析
        -> DirectorPlan
        -> Storyboard / AnimationPlan
        -> Remotion
        -> MP4
```

图片默认 `motion=static`，始终使用 contain 等比例适配：完整显示、不裁剪、不拉伸。视频时长由图片时间轴决定，BGM 由独立音频适配器循环或裁剪到最终时长。

## 2. 环境准备

需要 Python 3.11+、`uv`、Node.js、`pnpm`、`ffmpeg` 和 `ffprobe`。

```bash
uv sync
cd remotion && pnpm install && cd ..
uv run pytest -q
```

## 3. 配置 LLM

项目使用 OpenAI Compatible 接口，配置写入项目根目录 `.env`（不要提交）：

```env
LLM_PROVIDER=openai-compatible
OPENAI_BASE_URL=https://your-gateway.example/v1
OPENAI_API_KEY=your_key
LLM_MODEL=claude-sonnet-4-20250514
DIRECTOR_MODEL=claude-sonnet-4-20250514
REMOTION_MODEL=claude-sonnet-4-20250514
CHAT_MODEL=claude-sonnet-4-20250514
```

Claude、GPT、DeepSeek、Kimi 或 Ollama 只要兼容该接口即可切换。缺少 API Key 或设置 `LLM_PROVIDER=mock` 时使用 Mock Provider。

```bash
uv run python -m content_creator.llm_test
```

## 4. 普通视频生成

```bash
uv run python -m content_creator.main \
  --images ./input/images \
  --audio ./input/bgm.wav \
  --output ./output
```

主要参数：`--images` 图片目录，`--audio` 本地音频，`--output` 输出根目录，`--width`/`--height` 画布尺寸，`--fps` 帧率，`--preview` 预览渲染，`--style` 风格预设，`--director` 或 `--no-director` 控制 Director Agent，`--agent-mode` 启用 LangGraph 工作流。

输出项目目录：

```text
output/projects/<project_id>/
├── session.json
├── materials/
├── audio/
├── director_plan.json
├── render_data.json
└── render/final.mp4
```

## 5. Director Agent

Director Agent 接收 `ImageAsset`、`BeatAnalysis` 和风格，输出经 Pydantic 校验的 `DirectorPlan`。它只决定图片顺序、停留帧数、转场、情绪和可选 `animation_intent`，不生成 TSX、React、CSS 或 ffmpeg 命令。LLM 失败时回退到本地规则方案。

## 6. 交互式 Director Workspace

新建工作区：

```bash
uv run python -m content_creator.director_chat \
  --images ./input/images \
  --audio ./input/bgm.wav \
  --output ./output \
  --width 1080 --height 1920 --style cinematic
```

恢复已有工作区：

```bash
uv run python -m content_creator.director_chat \
  --project ./output/projects/<project_id>
```

两种启动方式不能同时使用。工作区创建时会保存绝对路径、图片分析、BGM 分析和 `session.json`，下游不会猜测 `Path("audio")` 或 `Path("images")`。

命令：`plan`、`show`、`show json`、`preview`、`render`、`save`、`help`、`quit` / `exit`。

普通输入会修改当前计划，例如“第一张从背面翻转进入”“第三张停留时间增加50%”。修改通过 `DirectorIntent` 和现有 Schema 校验，只尽量改动用户指定的场景。

## 7. Remotion Creative Agent

Creative Agent 将 `DirectorPlan.timeline[].animation_intent` 转为实现中立的 `AnimationPlan`，再由 Render Agent 写入 `render_data.json` 的 `timeline[].animation`。当前支持：

- `3d_card_flip` -> `card_flip_reveal` / `CardFlipReveal`
- `camera_push` -> `camera_push` / `CameraPush`
- `glitch`、`glitch_reveal` -> `glitch_reveal` / `GlitchReveal`
- `light_leak` -> `light_leak` / `LightLeak`

未知意图保留在 DirectorPlan，并使用 `FadeFallback` 安全预览。效果不改变图片 contain 几何，也不使用 `cover`、裁剪、`scaleX` 或 `scaleY`。

## 8. 渲染检查

```bash
cd remotion
pnpm exec tsc --noEmit
pnpm run build
pnpm exec remotion bundle src/index.ts /tmp/video-assistant-remotion-bundle
```

可用 `ffprobe` 检查输出尺寸、帧率、音频流和时长。
