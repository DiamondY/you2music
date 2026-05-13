# 配置说明（Env + 配置文件）

本项目仅支持 **ACE-Step (acemusic.ai)** 作为音乐生成 Provider。

配置加载优先级（高优先级覆盖低优先级）：

1. 环境变量（Env）
2. `config/providers.local.json`（本地私有配置，已在 `.gitignore` 中忽略）
3. `config/providers.json`（可选：团队共享配置）
4. 代码内默认值

推荐：复制 `config/providers.local.example.json` 为 `config/providers.local.json`，然后填入你的 `ACESTEP_API_KEY`。

---

## 1. 必需配置

### 1.1 ACE-Step API Key

- `ACESTEP_API_KEY`：ACE-Step (acemusic.ai) API Key

PowerShell 示例：

```powershell
$env:ACESTEP_API_KEY="YOUR_ACESTEP_KEY"
```

---

## 2. FastAPI 模式的认证配置（推荐使用时需要）

FastAPI 模式包含登录/注册与 JWT。你需要配置：

- `AI_MUSIC_JWT_SECRET`：JWT 签名密钥（建议使用足够长的随机字符串）

PowerShell 示例：

```powershell
$env:AI_MUSIC_JWT_SECRET="a-long-random-secret"
```

说明：
- stdlib 模式（`backend/stdlib_server.py`）不使用 JWT。

---

## 3. 常用可选配置

### 3.1 Provider / 输出

- `ACESTEP_BASE_URL`：ACE-Step API base_url（不要包含 `/v1`），默认 `https://api.acemusic.ai`
- `AI_MUSIC_OUTPUT_FORMAT`：默认输出格式（用于 UI 默认值/部分参数），默认 `mp3_44100_192`
- `AI_MUSIC_REQUEST_TIMEOUT_S`：后端请求上游 API 的超时（秒），默认 `120`

### 3.2 数据目录

- `AI_MUSIC_DATA_DIR`：数据落盘目录（SQLite + audio 文件），默认是项目根目录下的 `data/`

### 3.3 服务监听

- `AI_MUSIC_HOST`：监听地址，默认 `127.0.0.1`
- `AI_MUSIC_PORT`：监听端口，默认 `8000`

### 3.4 代理

你可以用环境变量（`httpx/urllib` 都能识别）：

- `HTTP_PROXY` / `http_proxy`
- `HTTPS_PROXY` / `https_proxy`
- `NO_PROXY` / `no_proxy`

也可以写到配置文件 `proxy` 字段中（见下文）。

---

## 4. 配置文件格式（`config/providers.local.json`）

示例（仅包含 ACE-Step）：

```json
{
  "secrets": {
    "acestep_api_key": "YOUR_ACESTEP_KEY"
  },
  "endpoints": {
    "acestep_base_url": "https://api.acemusic.ai"
  },
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
  "ui_defaults": {
    "acestep": {
      "model": "acemusic/acestep-v1.5-turbo",
      "audio_format": "mp3"
    }
  },
  "concurrency": {
    "acestep": { "max_concurrent": 1, "rate_limit_per_sec": 1.0, "cooldown_sec": 30.0 },
    "retry": { "max_retries": 3, "base_delay_sec": 2.0, "retryable_statuses": [429, 500, 502, 503, 504] },
    "queue_timeout_sec": 300
  }
}
```

字段说明（仅列当前代码实际读取/使用的部分）：

- `secrets.acestep_api_key`：API Key，支持单个字符串（向后兼容）或字符串数组（多 Key 轮询）
- `endpoints.acestep_base_url`：API base_url（只写 origin，不要包含 `/v1`）
- `ui_defaults`：UI 表单默认值（具体字段由 `/api/providers` 下发）
- `proxy`：会写入环境变量，供网络请求使用
- `server.host` / `server.port`：监听配置
- `auth.jwt_secret`：JWT secret（FastAPI 模式使用）
- `admin.username` / `admin.password` / `admin.default_daily_quota`：FastAPI 模式管理员初始化配置
- `concurrency`：队列/限流/重试配置

---

## 5. 多 Key 管理（轮询 + 健康追踪）

ACE-Step 支持配置多个 API Key，用于轮询与故障切换：

单 Key：
```json
"secrets": { "acestep_api_key": "key-abc-123" }
```

多 Key（字符串数组）：
```json
"secrets": { "acestep_api_key": ["key-abc-123", "key-def-456"] }
```

对象数组（只读取 `key` 字段）：
```json
"secrets": {
  "acestep_api_key": [
    { "key": "key-abc-123" },
    { "key": "key-def-456" }
  ]
}
```
