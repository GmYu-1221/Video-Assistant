# Video-Assistant 系统设计

## 1. 总体架构

```text
本地图片目录 ──> Asset Scanner / Image Processor
                         │
本地 BGM ───────> librosa Beat Analyzer
                         │
                         v
                 Director Agent / Rule Policy
                         │
                         v
                    DirectorPlan
                         │ Pydantic 校验
                         v
                     Storyboard
                         │
                         v
                  Render Agent / Timeline
                         │
                         v
                  Media Server + Remotion
                         │
                         v
                         MP4
```

Python 负责素材、音频、Schema、计划和渲染编排；Remotion 负责 Composition、Sequence、ImageFrame、TransitionSeries、Audio 和最终视频帧。

## 2. Agent 架构

当前代码包含 LangGraph 节点 `vision_agent`、`director_agent`、`remotion_agent` 和 `render_agent`。其中 Vision 使用本地 Pillow 规则分析，Director 可使用 OpenAI Compatible LLM 或本地规则回退，Remotion Agent 读取官方 Skill 文档并输出约束建议，Render Agent 将 Storyboard 编译为现有 Timeline。

```text
START
  -> vision_agent
  -> director_agent
  -> remotion_agent
  -> render_agent
  -> END
```

交互式 Director Chat 是独立 CLI，会对已有 `DirectorPlan` 应用增量 `DirectorIntent`，再调用现有渲染链路。

## 3. Director Agent 设计

LLM 不直接写 React、TSX、ffmpeg 或 Remotion 文件，只负责导演决策。

输入：

- `ImageAsset`：资源 ID、相对路径、尺寸、背景色、contain 配置。
- `BeatAnalysis`：时长、采样率、BPM、beats、downbeats、beat_strengths。
- `VideoStyle`：例如 `cinematic`、`dynamic`、`minimal`。

输出：

```json
{
  "timeline": [
    {
      "asset_id": "img001",
      "duration_frames": 120,
      "transition": {"type": "crossfade", "duration_frames": 8},
      "transition_strength": 0.5,
      "motion": "static",
      "reason": "Opening image establishes the mood."
    }
  ]
}
```

Pydantic 校验输入输出；资产顺序、转场注册、时长和静态 motion 不符合规则时使用确定性 fallback。

## 4. 数据结构

- `DirectorPlan`：导演输出的场景列表，唯一允许被 LLM 生成的计划协议。
- `DirectorTimelineItem`：单张图片的停留、转场、强度、运动状态和理由。
- `TimelineItem`：渲染阶段的绝对 `start_frame`、`end_frame` 和 `duration_frames`。
- `TransitionConfig`：统一的转场类型、帧数、方向、强度、缓动和背景色配置。
- `Storyboard` / `ScenePlan`：Render Agent 使用的兼容协议。

LLM 不直接提供 `start_frame` 和 `end_frame`，这些由本地时间轴编译器计算。

## 5. Remotion 渲染设计

Remotion 通过 `Root` 注册 `Slideshow` Composition。`Composition.tsx` 将 Timeline 映射为 `TransitionSeries.Sequence`，使用 `ImageFrame` 渲染图片，并通过转场 Registry 生成 `TransitionSeries.Transition`。Composition 的 `calculateMetadata` 根据 Timeline 末帧决定视频时长。

音频通过 `Audio` 组件播放 Media Server 提供的本地音频 URL。Media Server 只监听 `127.0.0.1`，只允许当前项目的 `materials/` 和 `audio/` 路径。

## 6. 图片安全设计

所有图片始终使用 `contain` 逻辑：按照视频画布和原图尺寸计算最大等比例缩放，居中显示并保留背景区域。

禁止：

- `object-fit: cover`
- crop / center-crop
- `scaleX` / `scaleY`
- 改变原始宽高比的强制拉伸

默认 `motion=static`。入场动画和转场必须与图片内部 motion 分离，不能使图片永久放大或平移出画布。

## 7. 转场系统设计

Python 的 `TransitionConfig` 描述转场意图；Remotion 的 Transition Registry 将类型映射到独立 Presentation。当前已实现基础、推入、擦除、闪切、whip、glitch、iris、digital wipe 等效果，并为未知或不稳定效果保留安全 fallback。

转场策略按 beat strength 和风格预设选择候选，并限制连续重复、高复杂度连续出现和过长 duration。Registry 是实现边界，Director 不生成组件代码。

## 8. LLM 扩展方向

未来可增加独立 Agent：

- 图片理解 Agent：提供信息密度、主体和构图分析。
- 音乐 Agent：提供更丰富的段落、高潮和能量分析。
- Director Agent：综合素材和音乐做镜头设计。
- Remotion Creative Agent：在约束内提出动画组件建议。
- 字幕 Agent：当前未实现，未来可作为独立模块。
- 音乐生成 Agent：当前只使用本地 BGM，不生成音乐。

所有扩展仍需通过 Pydantic Schema 和现有渲染安全规则。
