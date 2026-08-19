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
      RemotionCreativePlan（VisualEvent）
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

Web 文章转视频是另一条管线：文章 URL（或浏览器导入的 DOM）→ Article/Asset Agent 提取正文与图片 → 竖屏视觉规格与排版（Layout Director、Visual Critic）→ 渲染与字幕版本反馈。

普通模式保留旧的规则时间轴；`--agent-mode` 通过 LangGraph 编排 Vision、Director、Creative 和 Render 节点。

## 2. Session 与路径

Director Workspace 使用 `ProjectSession` 作为唯一上下文。它保存 `project_dir`、`images_dir`、`audio_path`、`source_audio_path`、输出目录、画布、FPS、风格、分析结果、当前计划、Storyboard、对话历史和渲染路径。所有路径序列化为绝对路径，恢复项目时不会依赖当前工作目录。会话文件为项目目录下的 `session.json`。

## 3. Director Agent

Director Agent 的输入是 `ImageAsset`、`BeatAnalysis` 和风格，输出严格的 `DirectorPlan`。LLM 只能做导演决策：时长、转场、节奏、情绪，以及场景创意意图 `creative_intent`（描述性视觉语言）与边界创意意图 `transition_intent`（描述性转场语言）。`start_frame`、`end_frame` 由本地编译器计算，LLM 不生成渲染代码。

交互式 Workspace 的自然语言修改通过 `DirectorPlanPatch` 实现：LLM 只返回针对指定场景的小型补丁（场景 ID + 需要修改的字段），由本地 `merge_director_plan_patch` 合并，避免 LLM 整体重写方案。

## 4. Creative Agent 与视觉计划

Creative Agent 读取 `.agents/skills/` 下的项目技能文档，将创意意图映射为注册的视觉事件。当前统一入口是 `create_remotion_creative_plan`，一次性输出 `RemotionCreativePlan`：

```json
{
  "plans": [{
    "scene_id": "image-001",
    "visual_events": [{
      "type": "particle_flip_reveal",
      "phase": "entrance",
      "start_frame": 0,
      "duration_frames": 24,
      "params": {"particle_density": 240, "rotation_axis": "Y"}
    }]
  }]
}
```

事件按阶段划分：`entrance`（入场）、`camera`（镜头）、`effect`（效果）、`transition`（场景边界转场）。逐场景的 `AnimationPlan` 与逐边界的 `TransitionEffectPlan` 能力表仍然保留；场景转场可选择注册表中启用的 `qwen3_8` 或 `zoom_whip_v2`。

每条事件都要通过阶段、帧范围、参数范围校验；非法事件被丢弃并记录日志，全部事件非法时回退到安全方案。另有一个独立的视觉规格决策 `create_visual_spec_decision`：选择画面布局（`center_stage` / `fullscreen`）与转场预设（`clean_cut` / `crossfade` / `white_flash` / `flash_zoom_blur`），决策失败时使用本地默认。

## 5. Remotion 渲染设计

`Composition.tsx` 负责组合 `TransitionSeries.Sequence`、`ImageFrame`、EffectRenderer 和 Audio。`EffectRegistry` 负责把动画名称映射到独立效果组件；Composition 不维护大量动画类型判断。Timeline 末帧决定视频总时长，音频适配到该时长。场景边界存在 qwen `transition_effect` 时走 `TransitionEffectRenderer`，否则直接硬切，不再调用旧转场工厂。

另注册了 `VisualSpec`、`TypographyFontShowcase`、`LayoutPreview` 三个 Composition，用于竖屏视觉规格渲染、字体展示与排版预览。

## 6. 图片安全设计

`ImageFrame` 按 `min(videoWidth/imageWidth, videoHeight/imageHeight)` 计算 contain 尺寸并居中。图片保持原始宽高比，空余区域由背景色填充；当前实现按画布最大 contain 尺寸计算，因此小图也可能被等比例放大。

禁止 `object-fit: cover`、crop、center-crop、`scaleX`、`scaleY` 和改变宽高比的拉伸。默认 `motion=static`；效果动画结束后返回未包装的原始图片场景（scale 1、rotate 0、translate 0、opacity 1、blur 0）。

## 7. 入场动画系统

效果目录为 `remotion/src/effects/`，通过 `remotion/src/effects/index.tsx` 的 `EffectRegistry` 注册：

- `CardFlipReveal`：CSS `rotateY` 卡片翻转入场。
- `CameraPush`：短暂 `translate` 叠层，底层保持完整图片；仅显式镜头语言（"缓慢推进"、Ken Burns 等）才会保留。
- `GlitchReveal`：确定性 RGB 偏移、切片和短暂滤镜。
- `LightLeak`：只增加 overlay，不改变图片尺寸。
- `StretchReveal`：丝滑拉伸入场，结束后恢复静止。
- `ElasticBlurReveal`：加权水平拉伸 + 垂直压缩 + 轻微镜头模糊，弹性回弹后完全静止（仅入场，18-36 帧）。
- `DropRevealElastic`：从指定方向落下并弹性回弹入场。
- `ParticleFlipReveal`：粒子面纱翻转入场。
- `CreativeReveal`：安全蒙版淡入，作为 LLM 不可用或校验失败时的默认降级。

实现使用当前已验证的 Remotion API：`useCurrentFrame`、`interpolate`、`spring`、`Easing` 和 React 样式。效果结束时恢复原始场景。

## 8. 转场与安全边界

转场意图通过 Python `TransitionConfig`（基线）与 `TransitionEffectPlan`（创意）分别进入 Remotion。动画 Registry 与转场 Registry 分离，两者都不能破坏 contain 规则。

旧的基线转场注册表已经删除，不再由风格预设决定场景边界效果。

场景转场通过 `template_transition` 和双端模板注册表接入。当前启用 `qwen3_8` 与 `zoom_whip_v2`；未知、禁用或非法模板会被拒绝，URL 图片边界的非法选择确定性回退到 qwen。

## 9. 视觉规格与排版系统

Web 文章转视频模式引入竖屏视觉规格与排版子系统：

- **VisualSpec**：结构化竖屏规格（1080x1920），描述布局预设、区域、图层、文本样式、动画轨道与转场预设，由 `VisualSpecComposition` 渲染。
- **Layout Director**（`LAYOUT_MODEL`）：根据文章文案与图片语义设计场景排版、文案密度与持续标题。
- **Visual Critic**（`VISUAL_CRITIC_MODEL`）：渲染中间帧后审查排版质量，得分低于 `LAYOUT_QA_THRESHOLD` 时触发一次本地化修复。
- **字体与偏好**：`TypographyPreferenceStore` 把用户反馈（`output/preferences/typography_feedback.jsonl`）沉淀为字体偏好；负反馈会触发 `revise_typography` 生成新的字幕版本（`versions/vNNN/`），保留版本快照、布局 QA 记录与预览帧。

## 10. Web 文章转视频

`content_creator.web`（FastAPI）提供单输入 Web 应用：提交文章 URL 后由 `create_url_project` 完成抓取、正文提取（`trafilatura` + BeautifulSoup）、中文化、候选缩略图视觉识别、全局素材排序、BGM 目录选曲、竖屏时间轴与渲染。任务在单 worker 队列中串行执行，进度通过 SSE 推送。

URL 素材采用“先看图、后选择”：规则过滤后的候选按正文来源信号预排，最多 24 张生成最长边 512px 的 JPEG 缩略图；多模态 Asset Agent 每批分析最多 6 张并返回 `CandidateVisualProfile`。所有批次合并后才统一排序，只有 `eligible=true` 的候选可进入原图下载及失败补位池。最终 `ImageTag` 直接继承视觉档案，避免对入选原图重复调用视觉模型。

- 网站禁止抓取时任务进入"等待浏览器导入"：页面提供 bookmarklet，用户在浏览器点击后把页面 DOM 回传本地服务（`/api/browser-import`，带令牌校验）。
- 每个任务保存版本快照（`versions/v001/` 等），支持按版本切换与反馈修订。

## 11. 扩展方向

可独立增加图片理解、音乐段落、字幕和更丰富的 Creative Agent，但所有输出必须先经过 Pydantic Schema、确定性策略和本地渲染安全检查。当前不接入数据库或云端媒体处理；Web 服务与所有渲染均为本地运行。
