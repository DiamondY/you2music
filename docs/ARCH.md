# 架构说明（当前实现）

目标：在不引入“平台级复杂度”的前提下，把 **Prompt/歌词 → 生成 → 试听/下载 → 留痕（SQLite）** 的端到端链路打通，同时保持 provider 可扩展、并发可控、排障成本低。

---

## 1. 两种运行模式

### A) FastAPI 模式（推荐）

- 入口：`backend/main.py`
- 依赖：`backend/requirements.txt`
- 特点：
  - 支持登录/注册（JWT）
  - 支持配额与管理员管理
  - 异步 worker + provider 队列（更适合长任务和并发控制）

### B) stdlib 模式（零依赖）

- 入口：`backend/stdlib_server.py`
- 依赖：仅 Python 标准库
- 特点：
  - 用于本地快速跑通（无登录/注册接口）
  - UI 会自动切换到“本地模式”（无需登录即可生成）

两种模式都复用同一套静态页面：`backend/static/index.html`。

---

## 2. 核心模块

### `backend/config.py`

配置加载：环境变量 → `config/providers.local.json` → `config/providers.json` → 默认值。

输出为 `Settings`（包含 base_url、api_key、默认 provider、并发配置、proxy 等）。

### `backend/storage.py`

SQLite 的 job store：

- 表：`jobs`
- 关键字段：`job_id`, `status`, `provider`, `prompt`, `params_json`, `output_path`, `error`
- 状态：`queued | running | succeeded | failed`

### `backend/user_store.py`（FastAPI 模式使用）

SQLite 的 user store：

- 用户：`users`
- 邀请码：`invite_codes`
- 配额消耗：`user_quotas`

### `backend/concurrency.py`

并发治理（FastAPI 模式）：

- `ProviderQueue`：按 provider 拆分队列，控制同时在跑的 worker 数量
- `TokenBucket`：按 provider 做简单的 rate limit
- `run_with_retry`：对上游短暂失败做指数退避重试

### `backend/workers.py`

FastAPI 模式的 job 执行入口：

- 从 provider 队列取 job
- 做 cooldown / rate limit / queue timeout
- 调用 provider client（MiniMax / ACE-Step）
- 写音频到 `data/audio/`，并更新 job 状态

### `backend/providers/*`

provider 客户端实现：

- `backend/providers/minimax.py` / `backend/providers/minimax_stdlib.py`
- `backend/providers/acestep.py` / `backend/providers/acestep_stdlib.py`
- `backend/providers/registry.py`：把 provider 元信息（UI 字段、默认值、能力）聚合成 `/api/providers` 输出

---

## 3. 典型请求链路（FastAPI）

1. 前端提交 `POST /api/generate` 或 `POST /api/generate_many`
2. 后端创建 job（`storage.JobStore.create_job()`），状态为 `queued`
3. 把 job_id 放入 provider 的 `ProviderQueue`
4. worker 将 job 状态置为 `running`，调用 provider API
5. 成功：写文件，状态置为 `succeeded`，提供 `/api/audio/{job_id}` 播放
6. 失败：状态置为 `failed`，错误信息写入 `error`
