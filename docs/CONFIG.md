# 配置说明（ENV Vars）

本项目通过环境变量配置运行参数（PowerShell 示例以 Windows 为主）。

也支持通过 **配置文件** 录入 provider 信息（推荐用于小范围工具，避免每次敲命令行设置 env vars）。

---

## 必需

### `ELEVENLABS_API_KEY`

ElevenLabs API Key（需要开通 Music 能力）。

```powershell
$env:ELEVENLABS_API_KEY="YOUR_KEY"
```

## 推荐：配置文件方式（无需敲命令行）

在项目目录下创建（或复制示例）：

- `config\providers.local.json`（本地私密配置，已在 `.gitignore` 中忽略）

你可以从示例复制：

- `config\providers.local.example.json`

其中可填写：

- 各 provider 的 key/token（`secrets`）
- 各 provider 的 base url（`endpoints`）
- 管理页面 token（`admin_token`）
- 代理（`proxy`）
- UI 默认值（`ui_defaults`）
- 默认 provider（`default_provider`）
- 启用的 provider 列表（`enabled_providers`，可选）

> 优先级：环境变量（env）会覆盖配置文件里的值，方便临时切换。

### `admin_token`（配置管理页面）

为了避免任何人打开 `/admin` 就能读写密钥，配置管理 API 需要 token 校验。

- 可通过环境变量：`AI_MUSIC_ADMIN_TOKEN`
- 或写在配置文件：`"admin_token": "..."`（更方便小范围使用）

### `proxy`（代理设置）

在配置文件中增加：

```json
{
  "proxy": {
    "http": "http://127.0.0.1:7890",
    "https": "http://127.0.0.1:7890",
    "no_proxy": "127.0.0.1,localhost"
  }
}
```

启动/加载时会将它映射到环境变量：

- `HTTP_PROXY`
- `HTTPS_PROXY`
- `NO_PROXY`

这样 `httpx` 与 `urllib` 都能自动走代理。

---

## 可选（常用）

### `AI_MUSIC_PROVIDER_DEFAULT`

默认 Provider（如果请求未指定 `provider`，就用这个）。

- 默认：`elevenlabs`

```powershell
$env:AI_MUSIC_PROVIDER_DEFAULT="elevenlabs"
```

### `FAL_KEY`

fal.ai API Key（用于 provider=`fal`）。

```powershell
$env:FAL_KEY="YOUR_FAL_KEY"
```

### `REPLICATE_API_TOKEN`

Replicate API Token（用于 provider=`replicate`）。

```powershell
$env:REPLICATE_API_TOKEN="YOUR_REPLICATE_TOKEN"
```

### `STABILITY_API_KEY`

Stability API Key（用于 provider=`stability`）。

```powershell
$env:STABILITY_API_KEY="YOUR_STABILITY_KEY"
```

### `AI_MUSIC_DATA_DIR`

数据落盘目录（SQLite + 音频文件）。

- 默认：`ai-music-tool\data`
- 影响：
  - SQLite：`<AI_MUSIC_DATA_DIR>\app.db`
  - 音频：`<AI_MUSIC_DATA_DIR>\audio\<job_id>.mp3`

```powershell
$env:AI_MUSIC_DATA_DIR="C:\Users\Administrator\Documents\Playground\ai-music-tool\data"
```

### `AI_MUSIC_OUTPUT_FORMAT`

ElevenLabs 输出格式（传给 `output_format`）。

- 默认：`mp3_192kbps`

```powershell
$env:AI_MUSIC_OUTPUT_FORMAT="mp3_192kbps"
```

---

## 可选（服务监听）

### `AI_MUSIC_HOST`

- 默认：`127.0.0.1`

```powershell
$env:AI_MUSIC_HOST="127.0.0.1"
```

### `AI_MUSIC_PORT`

- 默认：`8000`

```powershell
$env:AI_MUSIC_PORT="8000"
```

---

## 可选（Provider / 网络）

### `ELEVENLABS_BASE_URL`

ElevenLabs API base URL。

- 默认：`https://api.elevenlabs.io`
- 何时需要改：
  - 内网代理/网关
  - 自建兼容网关（极少）

```powershell
$env:ELEVENLABS_BASE_URL="https://api.elevenlabs.io"
```

### `FAL_QUEUE_BASE_URL`

fal queue base URL。

- 默认：`https://queue.fal.run`

```powershell
$env:FAL_QUEUE_BASE_URL="https://queue.fal.run"
```

### `FAL_PLATFORM_BASE_URL`

fal platform API base URL。

- 默认：`https://api.fal.ai`
- 用途：
  - `/api/admin/test` 会优先用 platform API 做鉴权/连通性检查（更权威）
  - 如果你自建了兼容网关，也可以用它来指向网关地址

```powershell
$env:FAL_PLATFORM_BASE_URL="https://api.fal.ai"
```

### `REPLICATE_BASE_URL`

Replicate API base URL。

- 默认：`https://api.replicate.com`

```powershell
$env:REPLICATE_BASE_URL="https://api.replicate.com"
```

### `STABILITY_BASE_URL`

Stability API base URL。

- 默认：`https://api.stability.ai`

```powershell
$env:STABILITY_BASE_URL="https://api.stability.ai"
```

### `AI_MUSIC_REQUEST_TIMEOUT_S`

HTTP 请求超时时间（秒）。

- 默认：`120`

```powershell
$env:AI_MUSIC_REQUEST_TIMEOUT_S="180"
```

---

## Python 3.14 + pip 安装（仅在 FastAPI 模式需要）

如果你需要安装 `backend\requirements.txt`，并且机器上存在 `tempfile` 目录不可写的问题：

- 使用脚本：`tools\pip_install_backend.ps1`
- 它会设置：
  - `PYTHONPATH=tools\py314_tempfile_fix`（加载 `sitecustomize.py`）
  - `PY_TEMP_BASE=<project>\.tmp_python`（把临时目录固定到项目内可写路径）
