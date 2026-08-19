# Video-Assistant 使用手册

## 1. 项目介绍

Video-Assistant 是一个本地优先的视频生成工具，提供三种使用方式：

- **命令行批量生成**：本地图片目录 + 本地 BGM，按节拍生成横屏或竖屏视频。
- **交互式 Director Workspace**：在终端里与导演助手对话，迭代修改导演方案后渲染。
- **Web 文章转视频**：输入公开文章 URL，自动提取正文与图片，生成竖屏短视频，并支持字幕版本反馈。
- **Viral Writer 文案策划**：URL 管线读取项目级 `.agents/skills/viral-writer`，生成五个中文标题候选和抖音短视频正文语义单元；模型失败时回退原文抽取。

它使用 Pillow 处理图片、librosa 分析 BGM 节拍，由规则管线或 Director Agent 生成导演方案，再由 Remotion 输出 MP4。

```text
图片素材 + 本地 BGM
        -> 图片/节拍分析
        -> DirectorPlan
        -> RemotionCreativePlan（VisualEvent）/ Storyboard
        -> Remotion
        -> MP4

文章 URL（Web 模式）
        -> 抓取 / 浏览器导入
        -> 正文提取与中文化
        -> 候选规则过滤（最多 24 张）
        -> 512px 缩略图多模态识别（每批最多 6 张）
        -> 合并视觉档案后全局排序
        -> 下载入选原图，失败时从合格池补位
        -> BGM 目录 -> 竖屏 1080x1920 视频
```

图片默认 `motion=static`，始终使用 contain 等比例适配：完整显示、不裁剪、不拉伸。视频时长由图片时间轴决定，BGM 由独立音频适配器循环或裁剪到最终时长。

## 2. 环境准备

需要 Python 3.11+、`uv`、Node.js、`pnpm`、`ffmpeg` 和 `ffprobe`。

```bash
uv sync
cd remotion && pnpm install && cd ..
uv run pytest -q
```

Web 模式的正文截图链路需要 Chromium（Playwright）：

```bash
make browser        # 等价于 uv run playwright install chromium
```

## 3. 配置 LLM

项目使用 OpenAI Compatible 接口，配置写入项目根目录 `.env`（不要提交）：

```env
LLM_PROVIDER=openai-compatible
OPENAI_BASE_URL=https://your-gateway.example/v1
OPENAI_API_KEY=your_key
LLM_MODEL=gpt-5.4
DIRECTOR_MODEL=gpt-5.4
REMOTION_MODEL=gpt-5.4
CHAT_MODEL=gpt-5.4
ASSET_MODEL=qwen3-vl-flash
ARTICLE_MODEL=gpt-5.4
LAYOUT_MODEL=gpt-5.4
VISUAL_CRITIC_MODEL=qwen3-vl-flash
LAYOUT_QA_THRESHOLD=0.78
URL_ASSET_CHARS_PER_IMAGE=1200
URL_ASSET_TARGET_MIN=1
URL_ASSET_TARGET_MAX=8
URL_BACKGROUND_VIDEO_DIR=./input/bgv
URL_MUSIC_DIR=./input/music
```

Claude、GPT、DeepSeek、Kimi 或 Ollama 只要兼容该接口即可切换。模型分工：

- `LLM_MODEL`：默认模型，未单独设置 Agent 模型时使用。
- `DIRECTOR_MODEL`：导演 Agent。
- `REMOTION_MODEL`：Remotion Creative Agent（动画与转场设计）和视觉规格决策。
- `CHAT_MODEL`：交互式 Director Workspace 的自然语言修改。
- `ASSET_MODEL`：Web 素材 Agent。它先读取 512px 缩略图生成视觉档案，再根据合并后的档案做一次全局排序；应配置支持图片输入的模型。
- `ARTICLE_MODEL`：文章理解 Agent；未配置时回退到 `ASSET_MODEL`。
- `LAYOUT_MODEL` / `VISUAL_CRITIC_MODEL`：动态场景排版与视觉审查；均回退到 `ASSET_MODEL`。
- `LAYOUT_QA_THRESHOLD`：视觉审查得分低于该值时触发一次本地化排版修复。
- `URL_ASSET_CHARS_PER_IMAGE` / `URL_ASSET_TARGET_MIN` / `URL_ASSET_TARGET_MAX`：Web 模式按 `clamp(ceil(正文字符数 / 1200), 1, 8)` 计算默认素材目标。
- `URL_BACKGROUND_VIDEO_DIR`：URL 视频随机背景素材目录；每个项目固定选择一次，短素材循环、长素材随主时间线裁剪。
- `URL_MUSIC_DIR`：URL 视频 BGM 目录；按文章主题、情绪和能量选曲。

缺少 API Key 或设置 `LLM_PROVIDER=mock` 时使用 Mock Provider（纯本地规则，不发送任何外部请求）。

```bash
uv run python -m content_creator.llm_test                     # 默认测试 director 路由
uv run python -m content_creator.llm_test --agent remotion     # 指定 agent 路由
uv run python -m content_creator.llm_test --agent asset
```

`--agent` 可选 `director`、`remotion`、`chat`、`asset`。

## 4. 普通视频生成（命令行）

```bash
uv run python -m content_creator.main \
  --images ./input/images \
  --audio ./input/bgm.wav \
  --output ./output
```

主要参数：

| 参数 | 说明 |
| --- | --- |
| `--images` | 图片目录（JPG/JPEG/PNG/WEBP） |
| `--audio` | 本地音频（WAV/MP3/M4A/FLAC） |
| `--output` | 输出根目录（默认 `output`） |
| `--width` / `--height` | 画布尺寸（默认 1920x1080） |
| `--fps` | 帧率（默认 30） |
| `--preview` | 预览渲染（较低 scale，更快） |
| `--transition-mode` | 已废弃的旧转场策略参数；新生产链路只使用注册表模板 |
| `--style` | 风格预设（见下表） |
| `--agent-mode` | 启用 LangGraph 工作流编排 Vision、Director、Creative、Render 节点 |
| `--director` / `--no-director` | 控制 Director Agent（默认自动：有可用 LLM 时启用） |

风格预设（`--style`）：

| 预设 | 基线转场 |
| --- | --- |
| 所有风格 | URL 图片边界从 `qwen3_8` / `zoom_whip_v2` 中选择；非法选择回退 `qwen3_8` |

输出项目目录：

```text
output/projects/<project_id>/
├── materials/images/          # 原始图片
├── materials/processed/       # 处理后图片
├── audio/                     # 原始音频 + bgm_adapted.wav
├── director_plan.json         # Director 方案（启用 Director 时）
├── render_data.json           # 渲染契约
└── render/final.mp4
```

## 5. Director Agent

Director Agent 接收 `ImageAsset`、`BeatAnalysis` 和风格，输出经 Pydantic 校验的 `DirectorPlan`。它只决定图片顺序、停留帧数、转场、情绪和可选的创意意图（`creative_intent` / `transition_intent`），不生成 TSX、React、CSS 或 ffmpeg 命令。LLM 失败时回退到本地规则方案。

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

两种启动方式不能同时使用（`--project` 与 `--images`/`--audio` 互斥）。工作区创建时会保存绝对路径、图片分析、BGM 分析和 `session.json`，下游不会猜测 `Path("audio")` 或 `Path("images")`。命令历史保存在项目目录的 `.director_history`。

命令：

- `plan`：生成或重新生成 DirectorPlan
- `show` / `show json`：查看当前方案和文案；`show json` 输出 JSON
- `preview`：用当前方案低分辨率预览渲染
- `render`：按原始尺寸渲染 final.mp4
- `save`：保存 session.json 和 director_plan.json
- `help`：查看帮助
- `quit` / `exit`：保存并退出

文案命令（不经过 LLM，直接写入 `video_copy`）：

- `设置标题：内容`
- `设置副标题：内容`
- `设置正文：内容`
- `清空文案`

普通输入会修改当前计划，例如"第一张从背面翻转进入""第三张停留时间增加50%"。修改通过 `DirectorPlanPatch` 和现有 Schema 校验，只尽量改动用户指定的场景；未配置 LLM（Mock 模式）时自然语言修改不可用。

## 7. Remotion Creative Agent

Creative Agent 将 `DirectorPlan` 中的创意意图转为实现中立的计划，再由 Render Agent 写入 `render_data.json`。当前统一入口为 `create_remotion_creative_plan`：一次性输出 `RemotionCreativePlan`（每个场景的 `visual_events` 列表，事件包含 `entrance` / `camera` / `effect` / `transition` 阶段）。逐边界 `TransitionEffectPlan` 只能引用注册表中启用的 `qwen3_8` 或 `zoom_whip_v2`。

入场/场景动画（注册于 `remotion/src/effects/index.tsx`）：

| 类型 | 组件 | 说明 |
| --- | --- | --- |
| `card_flip_reveal` | CardFlipReveal | 卡片式 3D 翻转入场 |
| `camera_push` | CameraPush | 缓慢镜头推进（需显式镜头语言，如"缓慢推进""Ken Burns"） |
| `glitch_reveal` | GlitchReveal | 数字故障层入场 |
| `light_leak` | LightLeak | 电影光漏入场 |
| `stretch_reveal` | StretchReveal | 丝滑拉伸入场 |
| `elastic_blur_reveal` | ElasticBlurReveal | 加权弹性拉伸 + 轻微镜头模糊入场（18-36 帧，结束后完全静止） |
| `drop_reveal_elastic` | DropRevealElastic | 从指定方向落下并弹性回弹入场 |
| `particle_flip_reveal` | ParticleFlipReveal | 粒子面纱翻转入场 |
| `creative_reveal` | CreativeReveal | 安全蒙版淡入（LLM 不可用时的默认降级） |

场景转场统一使用 `template_transition`，具体视觉由 `template_id` 指向双端注册的模板。当前启用 `qwen3_8` 和 `zoom_whip_v2`。LLM 不可用或输出校验失败时使用确定性的 qwen 参数；URL 视频的每个相邻图片边界都必须解析到一个完整注册转场。效果不改变图片 contain 几何，也不使用 `cover`、裁剪、`scaleX` 或 `scaleY`；效果结束后图片恢复完全静止。

视觉规格决策（`create_visual_spec_decision`）：由 Remotion Agent 额外选择画面布局（`center_stage` / `fullscreen`）。场景边界转场不再使用旧的 `crossfade`、`white_flash` 或 `flash_zoom_blur` 预设。

## 8. Web 文章转视频

启动本地 Web 服务：

```bash
make web
# 或：uv run uvicorn content_creator.web:app --host 127.0.0.1 --port 8000
```

浏览器打开 <http://127.0.0.1:8000>，输入公开文章 URL 并提交。页面会显示正文提取、缩略图生成、视觉识别、全局素材排序、文案编排和 Remotion 渲染进度。

素材选择顺序固定为：规则过滤 → 最多 24 张候选生成 512px 缩略图 → 多模态模型每批识别最多 6 张 → 合并 `CandidateVisualProfile` → 全局排序 → 下载合格原图。二维码、扫码推广、广告、合作伙伴卡片、页面 UI、Logo 和 App 下载图会在下载前排除，不能通过补位重新进入。模型不可用或个别候选失败时会使用 metadata、缩略图二维码检测和确定性排序继续生成。

- 部分网站禁止直接抓取时，任务会进入"等待浏览器导入"状态：把页面上的"导入当前文章"链接拖到书签栏，在文章页面点击，浏览器会把页面 DOM 回传给本地服务继续生成。
- 视频生成后可以切换版本；点击"不好看，重新设计字幕"并填写原因，会生成新的字幕版本（v002、v003……）。
- 字体与排版偏好记录在 `output/preferences/`（`typography_feedback.jsonl`），会持续影响后续视频的字幕设计。
- 需要 Chromium 截图链路时先执行 `make browser`。
- 每个 URL 项目会保存 `candidate_visual_profiles.json` 和 `asset_manifest.json`；后者包含候选、缩略图、视觉档案、全局排序、原图下载结果和最终成片图片映射。

## 9. 渲染检查

```bash
cd remotion
pnpm exec tsc --noEmit
pnpm run build
pnpm exec remotion bundle src/index.ts /tmp/video-assistant-remotion-bundle
```

可用 `ffprobe` 检查输出尺寸、帧率、音频流和时长。
