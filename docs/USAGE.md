# 使用指南（FastAPI + stdlib）

本项目提供两种运行方式：

- **FastAPI 模式（推荐）**：支持登录/注册、配额、管理员管理；需要安装 `backend/requirements.txt`
- **stdlib 模式（零依赖）**：仅用于本地快速体验（无需 pip）；不提供登录/注册，UI 会自动切换到“本地模式”

---

## 1. 配置（推荐用配置文件）

复制示例：

- `config/providers.local.example.json` -> `config/providers.local.json`

至少配置一个 provider 的 API key：

- `secrets.minimax_api_key` 或 `MINIMAX_API_KEY`
- `secrets.acestep_api_key` 或 `ACESTEP_API_KEY`

更多字段说明见：`docs/CONFIG.md`。

---

## 2. FastAPI 模式（推荐）

### 2.1 安装依赖并启动

```powershell
cd E:\Yww\DownLoad\source\you2music
python -m pip install -r .\backend\requirements.txt
$env:AI_MUSIC_JWT_SECRET="a-long-random-secret"
python .\backend\main.py
```

打开：

- UI：`http://127.0.0.1:8000/`
- Admin：`http://127.0.0.1:8000/admin`
- API 文档：`http://127.0.0.1:8000/docs`

### 2.2 UI 使用方式

1. 注册/登录
2. 在“生成”页填写 prompt（可选：歌词、时长、人声开关）
3. 提交后等待任务状态变为 `succeeded`，即可试听/下载

同一账号多端/多标签页同时打开时，任务状态会通过 SSE 自动同步（无需手动刷新）。

---

## 3. stdlib 模式（零依赖）

### 3.1 启动

```powershell
cd E:\Yww\DownLoad\source\you2music
python .\backend\stdlib_server.py
```

打开：

- UI：`http://127.0.0.1:8000/`

说明：
- stdlib 模式不提供 `/api/auth/*` 登录/注册接口。
- UI 会检测到后端不支持 auth，并自动切换到“本地模式”：无需登录即可生成。
