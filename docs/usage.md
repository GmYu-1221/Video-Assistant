# Video Assistant 使用说明

## 1. 环境要求

- Python 3.11 或更高版本
- `uv`
- Chromium（通过 Playwright 安装）
- FFmpeg 和 ffprobe
- 支持 OpenAI Chat Completions 协议的模型服务

安装依赖和浏览器：

```bash
make install
make browser
```

复制配置文件并填写本地密钥：

```bash
cp .env.example .env
```

至少需要配置：

```text
LLM_PROVIDER
OPENAI_BASE_URL
OPENAI_API_KEY
LLM_MODEL
```

可以为不同 Agent 单独指定模型：

```text
ARTICLE_MODEL
ASSET_MODEL
EDITORIAL_MODEL
COPY_FITTING_MODEL
DIRECTOR_MODEL
ANIMATION_MODEL
```

专用模型未设置时使用 `LLM_MODEL`。生产任务不接受 Mock Provider。

## 2. 启动 Web 服务

```bash
make web
```

浏览器打开：

```text
http://127.0.0.1:8000
```

页面提供三个 URL 输入框，第一个必填，第二和第三个可选。点击“生成视频”后，页面通过 SSE 显示以下阶段：

```text
文章处理
内容编排
导演设计
文案适配
分页编译
导演复核
动画生成
视频渲染
完成
```

## 3. Web API

### 创建任务

```http
POST /api/jobs
Content-Type: application/json

{
  "urls": [
    "https://example.com/a",
    "https://example.com/b"
  ]
}
```

约束：

- 最少 1 个 URL
- 最多 3 个 URL
- 只接受公开 HTTP/HTTPS 地址
- 重复 URL 会被去重
- 不接受旧的单数 `url` 字段

### 查询任务

```http
GET /api/jobs/{job_id}
```

示例响应：

```json
{
  "id": "job-id",
  "urls": ["https://example.com/a"],
  "status": "running",
  "stage": "导演设计",
  "progress": 62,
  "error": null,
  "browser_imports": [],
  "video_url": null
}
```

任务状态包括：

```text
queued
running
waiting_browser_import
completed
failed
```

### SSE 进度

```http
GET /api/jobs/{job_id}/events
```

任务完成或失败后 SSE 自动结束。等待浏览器导入时连接保持开启，导入后任务会继续执行。

### 查看或下载视频

```http
GET /api/jobs/{job_id}/video
```

任务成功后，查询接口中的 `video_url` 指向该地址。每个任务只有一个最终视频，不存在版本或反馈接口。

## 4. 浏览器导入回退

如果文章网站拒绝自动抓取，任务进入 `waiting_browser_import`，响应中的 `browser_imports` 会包含对应的 `source_id`、URL、HTTP 状态码和书签脚本。

操作步骤：

1. 把“导入当前文章”链接拖到浏览器书签栏。
2. 正常打开等待导入的文章页面。
3. 点击刚才保存的书签。
4. 页面提示导入成功后关闭导入页。
5. 返回 Video Assistant，任务会自动继续。

多 URL 任务会缓存已经完成的来源，只重新处理尚未完成的来源。

## 5. 输出文件

任务目录位于：

```text
output/projects/<job-id>/
```

常用文件：

- `source_results.json`：文章正文和本地素材
- `editorial_plan.json`：融合后的内容结构
- `viral_copy_plan.json`：短视频文案
- `timing_plan.json`：逐幕帧区间和屏幕可见文字的逐字段预算
- `presentation_plan.json`：scene 内各 display page 的素材、连续帧区间和实际字段预算
- `director_plan.json`：实现无关的导演方案
- `agent_runs/<agent>/attempt-*.txt`：结构化 Agent 每次原始响应
- `agent_runs/<agent>/validation.json`：Schema、ID、repair 和字段锁定校验结果
- `animation_response_attempt-1.txt` / `animation_response_attempt-2.txt`：Animation HTML 原始响应与最多一次 Contract repair 响应
- `animation_validation.json`：Animation 每次 HTML 校验结果及最终 `passed`、`passed_after_repair`、`failed` 或 `invocation_failed` 状态
- `sources/<source-id>/agent_runs/`：Article 四类结构化调用的逐批诊断
- `animation_prompt.json`：发送给动画模型的完整输入
- `animation.html`：模型生成的完整动画页面
- `animation_artifact.json`：渲染元数据
- `audio/bgm_adapted.wav`：适配到视频时长的背景音乐
- `render/final.mp4`：最终视频
- `render/validation.json`：编码、画幅、帧率和时长检查结果

## 6. 常用命令

```bash
make install   # 安装 Python 依赖
make browser   # 安装 Playwright Chromium
make web       # 启动 Web 服务
make test      # 运行测试
make clean     # 清理测试缓存和 Python 缓存
```

`make clean` 不会删除已经生成的项目和最终视频。

## 7. 常见失败

- `requires a configured non-mock LLM provider`：模型密钥或模型名未配置。
- `Browser import required`：目标网站拒绝自动抓取，需要执行浏览器导入。
- `Animation Agent must return one complete HTML document`：动画模型没有返回完整 HTML。
- `Forbidden animation feature`：HTML 使用了网络、计时器、路径越界或其他禁止能力。
- `Animation runtime meta mismatch`：HTML 中的画幅、FPS 或总帧数与计划不一致。
- `FFmpeg failed`：检查 FFmpeg 是否安装，以及 BGM 文件和编码器是否可用。
