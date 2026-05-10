# 配置说明（Env + 配置文件）

本项目的配置来源按优先级覆盖（高优先级覆盖低优先级）：

1. 环境变量（Env）
2. `config/providers.local.json`（本地私有配置，已在 `.gitignore` 中忽略）
3. `config/providers.json`（可选：团队共享配置）
4. 代码内默认值

推荐：复制 `config/providers.local.example.json` 为 `config/providers.local.json`，在文件里集中管理 key/base_url/默认 provider 等配置。

---

## 1. 必需配置

### 1.1 至少配置一个 Provider 的 API Key

二选一（或都配）：

- `MINIMAX_API_KEY`：MiniMax 官方 API Key
- `ACESTEP_API_KEY`：ACE-Step (acemusic.ai) API Key

PowerShell 示例：

```powershell
$env:MINIMAX_API_KEY="YOUR_MINIMAX_KEY"
# 或：
$env:ACESTEP_API_KEY="YOUR_ACESTEP_KEY"
```

---

## 2. FastAPI 模式的认证配置（推荐使用时需要）

FastAPI 模式包含登录/注册与 JWT。你需要配置：

- `AI_MUSIC_JWT_SECRET`：JWT 签名密钥（建议用足够长的随机字符串）

PowerShell 示例：

```powershell
$env:AI_MUSIC_JWT_SECRET="a-long-random-secret"
```

说明：
- stdlib 模式（`backend/stdlib_server.py`）不使用 JWT，也不提供登录/注册接口。

---

## 3. 常用可选配置

### 3.1 Provider / 输出

- `AI_MUSIC_PROVIDER_DEFAULT`：默认 provider（`minimax` 或 `acestep`），默认 `minimax`
- `MINIMAX_BASE_URL`：MiniMax API base_url（不要包含 `/v1`），默认 `https://api.minimaxi.com`
- `ACESTEP_BASE_URL`：ACE-Step API base_url（不要包含 `/v1`），默认 `https://api.acemusic.ai`
- `AI_MUSIC_OUTPUT_FORMAT`：默认输出格式（用于 UI 默认值/部分 provider 参数），默认 `mp3_44100_192`
- `AI_MUSIC_REQUEST_TIMEOUT_S`：后端请求上游 API 的超时时间（秒），默认 `120`

### 3.2 数据目录

- `AI_MUSIC_DATA_DIR`：数据落盘目录（SQLite + audio 文件），默认是项目根目录下的 `data/`

### 3.3 服务监听

- `AI_MUSIC_HOST`：监听地址，默认 `127.0.0.1`
- `AI_MUSIC_PORT`：监听端口，默认 `8000`

### 3.4 代理

你可以用环境变量（httpx/urllib 都能识别）：

- `HTTP_PROXY` / `http_proxy`
- `HTTPS_PROXY` / `https_proxy`
- `NO_PROXY` / `no_proxy`

也可以写到配置文件 `proxy` 字段中（见下文）。

---

## 4. 配置文件格式（`config/providers.local.json`）

文件结构（示例）：

```json
{
  "secrets": {
    "minimax_api_key": "YOUR_MINIMAX_KEY",
    "acestep_api_key": "YOUR_ACESTEP_KEY"
  },
  "endpoints": {
    "minimax_base_url": "https://api.minimaxi.com",
    "acestep_base_url": "https://api.acemusic.ai"
  },
  "default_provider": "minimax",
  "enabled_providers": ["minimax", "acestep"],
  "proxy": {
    "http": "http://127.0.0.1:7890",
    "https": "http://127.0.0.1:7890",
    "no_proxy": "127.0.0.1,localhost"
  },
  "server": {
    "host": "127.0.0.1",
    "port": 8000
  },
  "auth": {
    "jwt_secret": "a-long-random-secret"
  },
  "admin": {
    "username": "admin",
    "password": "change-me",
    "default_daily_quota": 20
  },
  "concurrency": {
    "minimax": { "max_concurrent": 3, "rate_limit_per_sec": 2.0 },
    "acestep": { "max_concurrent": 1, "rate_limit_per_sec": 1.0, "cooldown_sec": 30.0 },
    "retry": { "max_retries": 3, "base_delay_sec": 2.0, "retryable_statuses": [429, 502, 503, 504] },
    "queue_timeout_sec": 300
  }
}
```

字段说明（仅列当前代码实际读取/使用的部分）：

- `secrets.minimax_api_key` / `secrets.acestep_api_key`：provider 密钥，支持单个字符串（向后兼容）或字符串数组（多 Key 轮询）
- `endpoints.minimax_base_url` / `endpoints.acestep_base_url`：provider base_url
- `default_provider`：默认 provider
- `enabled_providers`：限制 UI 和后端允许的 provider 列表（可选）
- `ui_defaults`：provider 表单默认值（可选，具体字段由 `/api/providers` 下发）
- `proxy`：写入环境变量，供网络请求使用
- `server.host` / `server.port`：监听配置
- `auth.jwt_secret`：JWT secret（FastAPI 模式使用）
- `admin.username` / `admin.password`：初始管理员账号（FastAPI 模式使用）
- `admin.default_daily_quota`：新建用户默认配额（FastAPI 模式使用）
- `concurrency`：provider 队列/限流/重试配置

### 4.1 多 Key 管理（轮询 + 健康追踪）

每个 provider 可以配置多个 API Key，实现自动轮询和故障切换。

**配置格式：**

单个 Key（向后兼容）：
```json
"secrets": {
  "acestep_api_key": "key-abc-123"
}
```

多个 Key（数组形式，字符串或对象均可）：
```json
"secrets": {
  "acestep_api_key": ["key-abc-123", "key-def-456", "key-ghi-789"]
}
```

对象数组形式（仅使用 `key` 字段；`label` 当前实现会忽略，不会出现在日志/状态输出中）：
```json
"secrets": {
  "acestep_api_key": [
    {"key": "key-abc-123"},
    {"key": "key-def-456"}
  ]
}
```

**行为说明：**

| 场景 | 处理方式 |
|------|---------|
| Key A 收到 HTTP 429（限流） | 进入冷却期（默认 60s），指数退避后恢复可用 |
| Key A 收到 HTTP 401/403（认证失败） | 永久禁用，需重启服务或修改配置 |
| Key A 连续失败 N 次（默认 3 次） | 进入冷却期，防止影响整体成功率 |
| 所有 Key 均不可用（全部处于冷却期） | 等待最接近恢复的 Key，恢复后继续 |
| 所有 Key 均不可用（全部被禁用） | 不会自动恢复；需要更新配置/替换 Key，并重启或触发 reload 后才会恢复 |
| 单个 Key 配置 | 完全向后兼容，行为与之前一致 |

冷却时长可通过 `concurrency.<provider>.cooldown_sec` 配置。

连续失败阈值可通过 `concurrency.<provider>.max_failures` 配置（例如 `concurrency.acestep.max_failures`）。
