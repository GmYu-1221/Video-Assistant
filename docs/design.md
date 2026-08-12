# Video-Assistant 系统设计

## 1. 总体架构

```text
Input images / BGM
        |
        +--> Vision rules (Pillow)
        +--> Music analysis (librosa)
                    |
                    v
             Director Agent
                    |
                    v
              DirectorPlan
                    |
                    v
          Remotion Creative Agent
                    |
                    v
             AnimationPlan
                    |
                    v
        Storyboard / Timeline compiler
                    |
                    v
              Render Agent
                    |
                    v
          Remotion Composition -> MP4
```

普通模式保留旧的规则时间轴；`--agent-mode` 通过 LangGraph 编排 Vision、Director、Creative 和 Render 节点。

## 2. Session 与路径

Director Workspace 使用 `ProjectSession` 作为唯一上下文。它保存 `project_dir`、`images_dir`、`audio_path`、`source_audio_path`、输出目录、画布、FPS、风格、分析结果、当前计划、Storyboard、对话历史和渲染路径。所有路径序列化为绝对路径，恢复项目时不会依赖当前工作目录。

## 3. Director Agent

Director Agent 的输入是 `ImageAsset`、`BeatAnalysis` 和风格，输出严格的 `DirectorPlan`。LLM 只能做导演决策：时长、转场、节奏、情绪和 `animation_intent`。`start_frame`、`end_frame` 由本地编译器计算，LLM 不生成渲染代码。

## 4. Creative Agent 与 AnimationPlan

Creative Agent 读取官方 Remotion Skill 文档，按白名单将意图映射为 `AnimationEffect`：

```json
{
  "asset_id": "image-001",
  "effect": "card_flip_reveal",
  "component": "CardFlipReveal",
  "implementation": "custom",
  "duration_frames": 18,
  "props": {"perspective": 800, "rotateY": 180},
  "fallback": "none"
}
```

未知意图使用 `implementation=fallback`，保留原始意图类型，不让不支持的效果阻塞预览或正式渲染。

## 5. Remotion 渲染设计

`Composition.tsx` 负责组合 `TransitionSeries.Sequence`、`ImageFrame`、EffectRenderer 和 Audio。`EffectRegistry` 负责把动画名称映射到独立效果组件；Composition 不维护大量动画类型判断。Timeline 末帧决定视频总时长，音频适配到该时长。

## 6. 图片安全设计

`ImageFrame` 按 `min(videoWidth/imageWidth, videoHeight/imageHeight)` 计算 contain 尺寸并居中。图片保持原始宽高比，空余区域由背景色填充；当前实现按画布最大 contain 尺寸计算，因此小图也可能被等比例放大。

禁止 `object-fit: cover`、crop、center-crop、`scaleX`、`scaleY` 和改变宽高比的拉伸。默认 `motion=static`；效果动画结束后返回未包装的原始图片场景。

## 7. Effect 系统

当前效果目录为 `remotion/src/effects/`：

- `CardFlipReveal`：CSS `rotateY` 卡片翻转。
- `CameraPush`：短暂 `translate` 叠层，底层保持完整图片。
- `GlitchReveal`：确定性 RGB 偏移、切片和短暂滤镜。
- `LightLeak`：只增加 overlay，不改变图片尺寸。

实现使用当前已验证的 Remotion API：`useCurrentFrame`、`interpolate`、`Easing` 和 React 样式。效果结束时恢复原始场景。

## 8. 转场与安全边界

转场意图通过 Python `TransitionConfig` 进入 Remotion Transition Registry。动画 Registry 与转场 Registry 分离；两者都不能破坏 contain 规则。未知转场或动画使用安全 fallback。

## 9. 扩展方向

可独立增加图片理解、音乐段落、字幕和更丰富的 Creative Agent，但所有输出必须先经过 Pydantic Schema、确定性策略和本地渲染安全检查。当前不接入数据库、Web 服务或云端媒体处理。
