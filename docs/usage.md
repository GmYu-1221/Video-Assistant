# Video-Assistant 使用手册

## 1. 项目介绍

Video-Assistant 是一个本地图片目录到 MP4 的视频生成工具。它扫描本地图片，使用 Pillow 进行安全的等比例预处理，使用 librosa 分析本地 BGM 的 BPM、节拍和节拍强度，再由规则或 Director Agent 生成导演方案，最后交给 Remotion 渲染。

它解决了手工图片视频制作中素材整理、卡点、停留时间和转场配置重复的问题。完整链路是：

```text
图片分析 + 音乐分析
        -> DirectorPlan / 规则时间轴
        -> Storyboard
        -> Remotion
        -> MP4
```

项目默认保持 `motion=static`。图片使用 `contain` 等比例适配，不裁剪、不拉伸；BGM 由独立音频适配器循环或裁剪到视频时长。

## 2. 环境准备

要求：

- Python 3.11 或更高版本
- `uv`
- Node.js
- `pnpm`
- `ffmpeg` 和 `ffprobe`

安装 Python 依赖：

```bash
uv sync
```

安装 Remotion 依赖：

```bash
cd remotion
pnpm install
cd ..
```

检查：

```bash
uv run pytest -q
cd remotion && pnpm exec tsc --noEmit && pnpm run build
```

## 3. 配置 LLM

复制示例配置并编辑本地 `.env`：

```env
LLM_PROVIDER=openai-compatible
OPENAI_BASE_URL=https://your-gateway.example/v1
OPENAI_API_KEY=your_key
LLM_MODEL=claude-sonnet-4-20250514
DIRECTOR_MODEL=claude-sonnet-4-20250514
REMOTION_MODEL=claude-sonnet-4-20250514
CHAT_MODEL=claude-sonnet-4-20250514
```

项目使用 `openai` Python SDK 的 Chat Completions 接口。Claude、GPT、DeepSeek、Kimi 或本地 Ollama 只要提供 OpenAI Compatible 接口，就可以通过修改 `OPENAI_BASE_URL` 和模型名称切换。缺少 API Key，或明确设置 `LLM_PROVIDER=mock` 时，系统使用本地 Mock Provider，不发起网络请求。

测试当前配置：

```bash
uv run python -m content_creator.llm_test
```

## 4. 快速开始

准备图片目录和本地音频后运行：

```bash
uv run python -m content_creator.main \
  --images ./input/images \
  --audio ./input/bgm.wav \
  --output ./output
```

常用参数：

- `--images`：输入图片目录，支持项目已声明的 JPG/JPEG/PNG/WEBP 格式。
- `--audio`：本地 BGM 文件。
- `--output`：输出根目录，默认 `./output`。
- `--width`、`--height`：视频尺寸，默认 1920x1080。
- `--fps`：帧率，默认 30。
- `--preview`：以较低缩放比例进行预览渲染。
- `--director` / `--no-director`：显式启用或禁用 Director Agent；不指定时，只有检测到可用真实 Provider 才自动启用。
- `--agent-mode`：运行现有 LangGraph 工作流。
- `--style`：选择已有风格预设，例如 `cinematic`、`dynamic`、`minimal`。

生成结果位于：

```text
output/projects/<project_id>/
├── materials/
├── audio/
├── render_data.json
├── director_plan.json       # 启用 Director 后生成
└── render/final.mp4
```

## 5. Director Agent 使用

Director Agent 只负责导演决策，不直接修改 Remotion，也不生成代码。输入包括 `ImageAsset` 列表、`BeatAnalysis` 和视频风格；输出为经过 Pydantic 校验的 `DirectorPlan`。

它负责：

- 根据图片数量和 BGM 节拍规划停留时间。
- 按节拍强度选择转场意图和转场速度。
- 规划场景情绪、转场强度及未来可扩展的动画意图。
- 保持图片顺序、`motion=static` 和图片安全约束。

非法 JSON、未知转场、代码片段或网络调用失败都会回退到确定性的规则方案。

## 6. LLM 导演交互

先生成一个项目，然后启动交互式导演：

```bash
uv run python -m content_creator.director_chat
```

也可以指定项目：

```bash
uv run python -m content_creator.director_chat \
  --project ./output/projects/<project_id>
```

支持命令：`generate` 重新生成计划，`render` 渲染当前计划，`quit`/`exit` 退出。普通输入会作为当前计划的增量修改，不会重新生成全部方案。例如：

```text
Director> 第一张照片从背后翻转进入
Director> 转场更快一点
Director> 高潮部分更炸裂
Director> render
```

对话输出的是 `DirectorIntent`，例如 `3d_flip_in`、方向、速度和情绪；它不是 TSX。当前 Remotion 渲染仍遵守已实现的组件和转场注册表。

会话保存在项目目录的 `director_session.json`，当前计划保存在 `director_plan.json`。
