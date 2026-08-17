# content-creator（Video-Assistant）

本地优先的视频生成工具，提供三种使用方式：

- **命令行**：本地图片目录 + 本地 BGM 的节奏视频生成器。扫描并预处理 JPG/JPEG/PNG/WEBP 图片，用 librosa 分析 WAV/MP3/M4A/FLAC 的 BPM 和 beat，构建图片时间轴，通过 localhost Media Server 和 Remotion 输出 MP4。
- **交互式 Director Workspace**：终端对话迭代导演方案（图片顺序、停留帧数、创意入场动画、转场、文案），预览或正式渲染。
- **Web 文章转视频**：输入公开文章 URL，自动提取正文与图片，生成竖屏 1080x1920 短视频，并支持字幕版本反馈与字体偏好学习。

导演方案由 Director Agent（LLM，可回退到本地规则）生成，创意入场动画与转场由 Remotion Creative Agent 从已注册能力中选择，效果注册表含 9 种入场动画与 9 种创意转场。

## 环境

- Python 3.11+、uv
- Node.js 20+、pnpm
- FFmpeg（librosa 读取压缩音频通常需要）
- （Web 截图链路）Playwright Chromium：`make browser`

```bash
uv sync
cd remotion && pnpm install && cd ..
```

## 配置 LLM（可选）

OpenAI Compatible 接口，写入项目根目录 `.env`（不要提交），详见 [docs/usage.md](./docs/usage.md)。不配置密钥或设置 `LLM_PROVIDER=mock` 时使用本地 Mock Provider 渲染。

## 运行

命令行生成：

```bash
uv run python -m content_creator.main \
  --images ./input/images --audio ./input/bgm.wav
```

默认视频为 1920x1080、30 FPS，可用 `--width`、`--height`、`--fps`、`--style`、`--transition-mode` 修改。`--preview` 会以较低 scale 渲染；`--director`/`--no-director` 控制 Director Agent；`--agent-mode` 启用 LangGraph 工作流。

交互式 Director Workspace：

```bash
uv run python -m content_creator.director_chat \
  --images ./input/images --audio ./input/bgm.wav \
  --output ./output --style cinematic
```

Web 文章转视频：

```bash
make web     # 打开 http://127.0.0.1:8000
```

输出位于 `output/projects/<project_id>/`，包括 `materials/images`、`materials/processed`、`audio`、`render_data.json` 和 `render/final.mp4`。

## 测试与排错

```bash
uv run pytest -q
cd remotion && pnpm exec tsc --noEmit
```

如果没有图片、音频扩展名不支持、音频无法读取或 Remotion 依赖未安装，CLI 会直接报告错误。downbeat 检测不可靠时会自动使用 beat/BPM fallback。LLM 不可用时所有 Agent 自动回退到本地规则方案。

## 常用 Make 目标

```bash
make install   # uv sync + pnpm install
make test      # 运行 Python 测试
make render    # 用示例素材渲染
make web       # 启动文章转视频 Web 服务
make browser   # 安装 Playwright Chromium
```
