# Video Assistant 架构说明

## 1. 总体架构

项目将 1～3 篇公开文章处理为一条中文竖屏视频。唯一生产链路为：

```text
Web 输入 URL
→ 素材来源 Agent
→ 内容编排 Agent
→ 导演 Agent（决定总秒数、场景和相对时长权重）
→ Timing Compiler（生成确定帧区间）
→ 文案适配 Agent
→ 导演复核（最多要求压缩两次）
→ 动画 Agent
→ AnimationArtifact
→ HTML 校验器
→ Chromium 逐帧渲染
→ FFmpeg + BGM
→ final.mp4
```

系统分为两个明确边界：

- LangGraph 只负责 Agent 决策、数据传递和文案修订回环。
- Chromium 与 FFmpeg 是确定性执行层，不属于 Agent，也不进入 Graph。

项目没有固定动画模板，也不会在模型失败后生成降级 HTML。任一 Agent 使用 Mock、调用失败或返回非法内容时，整个任务立即失败。

### Structured Agent Contract

Article、Editorial、Director、Copy Fitting 和 Director Review 的结构化调用统一经过 `StructuredAgentRunner`：

- 只接受单个 JSON object，Markdown fence、解释文字和额外字段均视为校验失败。
- Agent 输出 DTO 递归使用 `extra="forbid"`、严格类型、显式必填字段、枚举和数量范围。
- 引用 ID 必须来自本次输入并由 Python 校验；beat ID 和 scene ID 由 Python按顺序生成。
- 首次 Schema 或业务引用校验失败时只允许一次 repair。repair 只能修改 `error_paths` 以及 validator 明确给出的 `related_paths`，其余合法值、对象结构和数组顺序必须保持不变。
- 网关只有明确声明不支持 `response_format/json_schema` 时才降级到 JSON object mode；鉴权、模型不存在、限流、超时和服务端错误直接失败。
- 每次调用保存原始 attempt 和 validation JSON。Animation Agent 不使用本 Contract，继续执行独立 HTML Contract。

## 2. Agent 工作流

### 素材来源 Agent

每个 URL 使用独立的 `source-001`、`source-002`、`source-003` 标识。多个来源可以并发处理，但最终统一汇总为 `source_results`。

该节点复用既有的确定性工具完成：

- 网页抓取、正文提取与 HTML 清洗
- 浏览器导入回退
- 素材发现、候选缩略图生成和多模态筛选
- 图片下载、本地化和 WebP 统一处理
- 英文说明文案中文化

Agent 负责语义选择，不重新实现底层抓取和图片处理。

Article 范围内的正文候选选择、逐批中文化、素材视觉分析和素材全局选择保持独立职责与原有顺序，但共享同一 Structured Agent Contract。翻译每批最多 7 段，限制不作用于整篇文章；视觉分析每批最多 6 张图。

### 内容编排 Agent

内容编排 Agent 负责跨来源融合、去重、主观点、内容优先级和叙事结构。模型不生成 beat ID；Python 使用 `beat-001`、`beat-002` 顺序编号。每个事实点必须引用：

```json
{
  "source_id": "source-001",
  "paragraph_index": 3
}
```

不存在的来源或段落引用会被拒绝。

### 导演 Agent 与 Timing Compiler

导演根据内容编排的信息量、核心 beat 数量、实际可用素材数量和整体节奏，决定 15～90 秒的整数 `duration_seconds`、scene 划分及每幕正数 `duration_weight`。模型不输出 width、height、FPS、scene ID、`duration_frames` 或帧边界；Python 注入项目参数、使用 `scene-001` 顺序编号，并唯一使用 `duration_seconds * project.fps` 计算总帧数。

Timing Compiler 使用稳定的最大余数法分配帧：每幕先保证一帧，再按权重分配剩余帧，余数相同时按 scene 顺序处理。生成的半开区间从第 0 帧开始、连续无空洞，并准确结束于 `duration_frames`。默认按中文每秒 7 字计算各幕 `text_budget`。

导演只输出实现无关的视觉方案，不能输出 DOM、CSS 代码、动画 API 或框架组件。scene ID 必须唯一，素材 ID 必须存在，权重必须为正。

### 文案适配 Agent

文案适配 Agent 只生成 `viral_copy_plan`，不能输出或修改时长、FPS、scene、权重或帧区间。输入中的 `timing_plan`、每幕秒数与 `text_budget` 均已锁定；文案 scene ID 和顺序必须与导演方案完全一致。

该节点加载项目内的 Viral Writer 技能，用于标题、钩子、信息密度和事实可追溯性。

### 导演复核

导演复核只能接受文案或给出压缩目标，不能修改总时长、scene、权重或帧区间。最多允许两次文案修订，第三次仍不通过则任务失败，`timing_plan` 在整个回环中保持不变。

### 动画 Agent

动画 Agent 接收完整的来源结果、内容方案、文案方案、时间方案、导演方案、本地素材预览、字体白名单和 HTML 运行协议。

模型通过 `ANIMATION_MODEL` 调用；未配置时回退到 `LLM_MODEL`。输出必须是一份完整 HTML 文档，不能只返回代码片段或说明文字。

## 3. HTML 运行协议

生成的 `animation.html` 必须加载本地 GSAP 3.15.0：

```html
<script src="runtime/gsap.min.js"></script>
```

必须创建唯一的暂停主时间线：

```js
const masterTimeline = gsap.timeline({paused: true});
```

并暴露以下全局接口：

```js
window.__ANIMATION_META__ = {
  width: 1080,
  height: 1920,
  fps: 30,
  durationFrames: 300
};

window.__ANIMATION_READY__ = false;

window.renderFrame = async function (frame) {
  const fps = window.__ANIMATION_META__.fps;
  const time = frame / fps;
  masterTimeline.time(time, false);
  await document.fonts.ready;
};
```

图片和字体加载完成后才能将 `window.__ANIMATION_READY__` 设为 `true`。同一个 frame 被重复渲染时，视觉结果必须一致。

HTML 校验器会拒绝：

- 远程 URL、CDN、远程图片、视频和字体
- `fetch`、XHR、WebSocket、EventSource
- iframe、object、embed
- 动态 import、eval、Function constructor
- 路径越界和白名单目录之外的资源
- CSS animation、CSS transition、定时器和 requestAnimationFrame
- 真实时钟、随机数和自动播放主时间线

允许访问的相对资源根目录只有 `materials/`、`runtime/` 和 `background/`。

## 4. Chromium 与 FFmpeg

Graph 返回 `AnimationArtifact` 后，普通 Python Service 执行渲染：

1. 在本机回环地址启动项目静态服务。
2. Chromium 拦截并阻止所有非项目本地请求。
3. 等待 `window.__ANIMATION_READY__ === true`。
4. 再次确认字体和所有图片已经加载。
5. 校验运行元数据与 AnimationArtifact 一致。
6. 对每一帧调用并等待 `window.renderFrame(frame)`。
7. 获取 PNG bytes，并直接写入 FFmpeg `image2pipe` stdin。

中间 PNG 不落磁盘。最终视频使用：

- H.264 视频编码
- `yuv420p` 像素格式
- AAC 音频编码
- `audio/bgm_adapted.wav` 背景音乐
- `duration_frames / fps` 作为严格时长

## 5. 项目产物

每个任务写入：

```text
output/projects/<job-id>/
├── project.json
├── source_results.json
├── editorial_plan.json
├── viral_copy_plan.json
├── copy_fitting_response.txt
├── copy_fitting_validation.json
├── copy_fit_decision.json
├── agent_runs/
│   ├── editorial/
│   ├── director/
│   ├── copy_fitting/
│   └── director_review/
│       ├── attempt-1.txt
│       ├── attempt-2.txt（仅发生 repair 时）
│       └── validation.json
├── timing_plan.json
├── director_plan.json
├── animation_prompt.json
├── animation_artifact.json
├── animation.html
├── runtime/
│   ├── gsap.min.js
│   └── fonts/
├── materials/
├── sources/
│   └── source-001/agent_runs/（正文选择、翻译批次、视觉批次、素材选择）
├── audio/
│   ├── bgm_adapted.wav
│   └── selection.json
└── render/
    ├── final.mp4
    └── validation.json
```

失败任务保留已经完成的 JSON、HTML 和诊断文件，但不会暴露 `video_url`。
