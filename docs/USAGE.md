# 使用指南（FastAPI + stdlib 双模式）

本项目提供两种运行方式：

- **FastAPI 模式（推荐）**：接口更标准，带 `/docs` 文档页；需要先安装 `backend\requirements.txt`。
- **零依赖 stdlib 模式**：只用 Python 标准库，不需要 pip；适合在依赖安装受限的环境快速跑通。

> 说明：本工具默认对接 **ElevenLabs Music API**，支持“人声唱歌（vocals）/纯器乐（instrumental）”、多候选（variations）、延长（extend）。

---

## 1. 环境变量

### 必需

- `ELEVENLABS_API_KEY`：你的 ElevenLabs API Key（需要开通 Music 能力）

PowerShell 示例：

```powershell
$env:ELEVENLABS_API_KEY="YOUR_KEY"
```

### 可选

- `AI_MUSIC_DATA_DIR`：数据目录（SQLite + 音频文件），默认 `ai-music-tool\data`
- `AI_MUSIC_OUTPUT_FORMAT`：输出格式，默认 `mp3_44100_192`
- `AI_MUSIC_HOST`：监听地址，默认 `127.0.0.1`
- `AI_MUSIC_PORT`：监听端口，默认 `8000`
- `ELEVENLABS_BASE_URL`：API base（一般不用改），默认 `https://api.elevenlabs.io`
- `SUNO_API_KEY`：Suno 第三方 API Key（用于 provider=`suno`）
- `SUNO_BASE_URL`：Suno 第三方 API base（用于 provider=`suno`），默认 `https://api.musicapi.ai`

---

## 2. FastAPI 模式（推荐）

### 2.1 启动

```powershell
cd C:\Users\Administrator\Documents\Playground\ai-music-tool\backend
python .\main.py
```

打开：

- Web UI：`http://127.0.0.1:8000`
- Swagger：`http://127.0.0.1:8000/docs`
- ReDoc：`http://127.0.0.1:8000/redoc`
- 配置管理：`http://127.0.0.1:8000/admin`（需要 admin token）

### 2.2 用 Web UI

页面功能：

- **生成**：生成单首歌曲/音乐
- **生成多候选**：一次生成 2–4 个候选（列表可逐个试听、切换）
- **延长当前**：对当前选中的 job “延长”若干秒

“人声唱歌”建议：

- 打开 `人声唱歌`
- Prompt 写清楚（例如：`with vocals, singing`）
- 尽量提供歌词（副歌/主歌分段）

### 2.2.1 Provider 动态切换与参数

UI 支持按 **provider** 动态切换：

- Provider 下拉框：选择 `elevenlabs`（当前内置）
- 模式：`普通 / 高级`
  - 普通：只显示少量常用 provider 参数
  - 高级：显示更多 provider 专有参数（含 JSON 参数）

后端会提供 provider 元信息与表单字段定义：

- `GET /api/providers`

### 2.3 用 API（curl 示例）

> Windows PowerShell 里建议用 `Invoke-RestMethod`；下面给的是通用 curl 形式（你也可以在 `/docs` 里直接点）。

#### 生成（单首）

`POST /api/generate`

```bash
curl -s http://127.0.0.1:8000/api/generate ^
  -H "content-type: application/json" ^
  -d "{\"prompt\":\"一首温柔的中文流行歌，女声演唱，副歌抓耳\",\"lyrics\":\"主歌...\\n\\n副歌...\",\"duration_sec\":45,\"vocals\":true,\"seed\":null,\"model_id\":null,\"provider\":\"elevenlabs\",\"provider_params\":{\"output_format\":\"mp3_44100_192\"}}"
```

返回：

- `{"job_id":"..."}`

#### 生成（Suno 第三方 API）

`POST /api/generate`

> Suno 是通过第三方 API 服务商接入（例如 musicapi.ai）。请先配置 `SUNO_API_KEY` / `SUNO_BASE_URL`，并在请求中指定 `provider="suno"`。

```bash
curl -s http://127.0.0.1:8000/api/generate ^
  -H "content-type: application/json" ^
  -d "{\"prompt\":\"一首中文流行歌，女声，副歌抓耳\",\"lyrics\":null,\"duration_sec\":30,\"vocals\":true,\"seed\":null,\"model_id\":null,\"provider\":\"suno\",\"provider_params\":{\"model\":\"v4.5\",\"instrumental\":false,\"poll_interval_s\":2.0}}"
```

#### 生成多候选（2–4 首）

`POST /api/generate_many`

```bash
curl -s http://127.0.0.1:8000/api/generate_many ^
  -H "content-type: application/json" ^
  -d "{\"prompt\":\"电子舞曲，男声唱，适合短视频\",\"lyrics\":null,\"duration_sec\":30,\"vocals\":true,\"seed\":null,\"model_id\":null,\"count\":3,\"provider\":\"elevenlabs\",\"provider_params\":{\"output_format\":\"mp3_44100_192\"}}"
```

返回：

- `{"job_ids":["...","...","..."]}`

#### 查询 job（单个）

`GET /api/jobs/{job_id}`

```bash
curl -s http://127.0.0.1:8000/api/jobs/<JOB_ID>
```

返回关键字段：

- `status`: `queued` / `running` / `succeeded` / `failed`
- `audio_url`: 成功后提供可播放/下载的 URL
- `error`: 失败原因（如果有）

#### 查询多个 job（用于多候选轮询）

`GET /api/jobs?ids=id1,id2,id3`

```bash
curl -s "http://127.0.0.1:8000/api/jobs?ids=<ID1>,<ID2>,<ID3>"
```

#### 延长（Extend）

`POST /api/extend`

```bash
curl -s http://127.0.0.1:8000/api/extend ^
  -H "content-type: application/json" ^
  -d "{\"job_id\":\"<JOB_ID>\",\"extra_sec\":15,\"provider\":\"elevenlabs\",\"provider_params\":{\"output_format\":\"mp3_44100_192\"}}"
```

返回：

- `{"job_id":"<NEW_JOB_ID>","parent_job_id":"<JOB_ID>"}`

> 注意：目前的 Extend 是“用相同 prompt/参数生成更长版本”，不是对旧音频无缝续写拼接。

---

## 3. 零依赖 stdlib 模式（无需 pip）

### 3.1 启动

```powershell
cd C:\Users\Administrator\Documents\Playground\ai-music-tool
python .\backend\stdlib_server.py
```

打开：

- `http://127.0.0.1:8000`
- 配置管理：`http://127.0.0.1:8000/admin`（需要 admin token）

> “保存/应用”后会在当前进程内热加载配置（包括 provider 启用列表、密钥、代理、数据目录）。通常不需要重启服务。

### 3.2 接口差异

UI 与 API 路径与 FastAPI 版本保持一致（`/api/generate`, `/api/generate_many`, `/api/extend`, `/api/jobs...`）。

---

## 4. 数据落盘位置

默认在：

- 数据库：`ai-music-tool\data\app.db`
- 音频文件：`ai-music-tool\data\audio\<job_id>.mp3`

你可以用 `AI_MUSIC_DATA_DIR` 自定义目录。

---

## 5. 常见问题排查

### 5.1 生成失败 / 401 / 403

- 确认 `ELEVENLABS_API_KEY` 设置正确
- 确认账号开通 Music 能力、额度足够

### 5.2 明明开了 vocals 但不唱歌

- Prompt 更明确：加入 `with vocals, singing`
- 提供歌词，并分段（主歌/副歌）
- 避免写“纯器乐/背景音乐”等互相矛盾的描述

### 5.3 下载/播放 404

先查 job 状态：

- `GET /api/jobs/<job_id>`

必须是 `succeeded` 且返回 `audio_url` 才能播放/下载。
