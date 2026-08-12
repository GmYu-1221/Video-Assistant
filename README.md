# content-creator

本地图片目录 + 本地 BGM 的节奏视频生成器。它扫描并预处理 JPG/JPEG/PNG/WEBP 图片，用 librosa 分析 WAV/MP3/M4A/FLAC 的 BPM 和 beat，构建 2～8 拍的图片时间轴，再通过 localhost Media Server 和 Remotion 输出 MP4。

## 环境

- Python 3.11+、uv
- Node.js 20+、pnpm
- FFmpeg（librosa 读取压缩音频通常需要）

```bash
uv sync
cd remotion && pnpm install && cd ..
```

## 运行

```bash
PYTHONPATH=src python -m content_creator.main \
  --images ./input/images --audio ./input/bgm.wav
```

默认视频为 1920x1080、30 FPS，可用 `--width`、`--height`、`--fps` 修改。`--preview` 会以较低 scale 渲染。

输出位于 `output/projects/<project_id>/`，包括 `materials/images`、`materials/processed`、`audio`、`render_data.json` 和 `render/final.mp4`。

## 测试与排错

```bash
PYTHONPATH=src python -m pytest -q
cd remotion && pnpm exec tsc --noEmit
```

如果没有图片、音频扩展名不支持、音频无法读取或 Remotion 依赖未安装，CLI 会直接报告错误。downbeat 检测不可靠时会自动使用 beat/BPM fallback。
