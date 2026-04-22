# 架构说明（小范围工具）

目标：在不追求“平台级复杂度”的前提下，把 **Prompt → 生成（可唱歌）→ 试听/下载 → 留痕** 的技术链路打通，并保持可替换性（将来可接入其他音乐 API 或自托管推理服务）。

---

## 1. 两种运行模式

### A) FastAPI 模式（推荐）

- 入口：`backend\main.py`
- 依赖：`backend\requirements.txt`
- 优点：
  - API 结构更标准
  - `/docs`、`/redoc` 自动生成接口文档
  - 后续加鉴权/限流/中间件更方便

### B) stdlib 零依赖模式

- 入口：`backend\stdlib_server.py`
- 依赖：Python 标准库（无需 pip）
- 优点：
  - 在依赖安装受限的机器上也能跑
  - 便于快速验证功能链路

两种模式的 UI 与核心 API 路径保持一致：

- `POST /api/generate`
- `POST /api/generate_many`
- `POST /api/extend`
- `GET /api/jobs/{job_id}`
- `GET /api/jobs?ids=...`
- `GET /api/audio/{job_id}.mp3`
- `GET /api/providers`（provider 列表与参数 schema）

---

## 2. 主要模块

### `backend\config.py`

配置加载（环境变量 → `Settings`）：

- `ELEVENLABS_API_KEY`
- `AI_MUSIC_DATA_DIR`
- `AI_MUSIC_OUTPUT_FORMAT`
- `AI_MUSIC_REQUEST_TIMEOUT_S`
- `ELEVENLABS_BASE_URL`

### `backend\storage.py`

SQLite job 存储（用于排查、复现、回溯）：

- 表：`jobs`
- 字段（核心）：`job_id`, `status`, `prompt`, `params_json`, `output_path`, `error`
- 扩展字段：`kind`, `parent_job_id`（用于区分 generate/variation/extend，并建立派生关系）
- `status`：`queued | running | succeeded | failed`

### `backend\providers\elevenlabs.py`（FastAPI 用）

通过 `httpx` 调用 ElevenLabs Music API（异步）。

### `backend\providers\elevenlabs_stdlib.py`（stdlib 用）

通过 `urllib.request` 调用 ElevenLabs Music API（无第三方依赖）。

---

## 3. 关键产品能力与实现说明

### 3.1 “人声唱歌（vocals）”

在请求中：

- `vocals=true` → 发送给 provider：`force_instrumental=false`
- `vocals=false` → 发送给 provider：`force_instrumental=true`

同时后端会对 Prompt 做轻微“提示增强”：

- vocals on：追加 `with vocals, singing ...`
- vocals off：追加 `instrumental only ...`

### 3.1.1 Provider 动态切换 + 参数（per-request）

请求体支持：

- `provider`：每次请求指定 provider（不传则使用 `AI_MUSIC_PROVIDER_DEFAULT`）
- `provider_params`：provider 专属参数对象

UI 不写死表单：前端通过 `GET /api/providers` 获取字段定义并动态渲染（支持普通/高级模式）。

### 3.2 多候选（variations）

`POST /api/generate_many`：

- 一次创建 2–4 个 job（`kind="variation"`）
- 每个 job 独立调用 provider（结果彼此不同）
- UI 用 `GET /api/jobs?ids=...` 一次轮询多个任务

### 3.3 延长（extend）

`POST /api/extend`：

- 依赖一个已完成的 parent job（`status=succeeded`）
- 新建一个子 job（`kind="extend"`, `parent_job_id=<parent>`）
- **当前实现策略**：把 `duration_sec` 增加 `extra_sec`，然后用相同 prompt/参数 **重新生成更长版本**

> 这不是“无缝续写/拼接”，而是 best-effort 的“更长重生成”。如果未来接入的 provider 支持真正的续写/continuation，可以把 extend 实现替换成 provider 的原生能力（或做音频拼接+淡入淡出）。

---

## 4. 可替换点（以后接入别家 API 怎么做）

目前 provider 是“写死为 ElevenLabs”，但你可以把它抽象成接口（建议方向）：

- `compose(prompt, length_ms, force_instrumental, seed, model_id, output_format) -> audio_bytes`

如果接入另一个 API（例如支持 native extend 的服务）：

- 为新服务新增一个 `backend\providers\<name>.py`
- 在 `main.py / stdlib_server.py` 里根据配置选择 provider
- 把 `extend` 从“重生成”改为“原生续写 + 拼接/版本化”

---

## 5. 目录结构（概览）

- `backend\main.py`：FastAPI 入口
- `backend\stdlib_server.py`：零依赖 HTTP server 入口
- `backend\static\index.html`：单页 UI
- `backend\storage.py`：SQLite job store
- `backend\config.py`：配置
- `backend\providers\`：provider 实现（ElevenLabs）
- `data\`：默认数据目录（运行时生成）
- `docs\`：文档（USAGE/CONFIG/ARCH）
- `tools\`：安装/兼容性脚本（含 Python 3.14 tempfile 修复）
