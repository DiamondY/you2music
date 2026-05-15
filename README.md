# you2music

**小范围内部工具，通过 ACE-Step (acemusic.ai) API 生成音乐，支持歌词/人声切换、延长、多 key 轮询、API 日志审计。**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

---

## 这是什么（不是什么）

- ✅ Prompt → 音乐生成 → 试听/下载的端到端流程
- ✅ 仅支持 ACE-Step provider
- ✅ 人声开关 + 歌词输入
- ✅ 多候选生成（2–4 种变体）
- ✅ 延长（重新生成更长版本）
- ✅ 多 API Key 轮询 + 健康追踪 + 故障自动切换
- ✅ SQLite 审计日志（提示词/参数/时间）
- ✅ API 调用日志（请求/响应/状态/耗时）—— 管理后台可见
- ✅ SQLite 任务队列 + 并发控制
- ✅ JWT 认证 + 用户配额 + 邀请码管理
- ✅ 同一账号多端 SSE 实时同步
- ✅ FastAPI 模式（推荐）+ stdlib 零依赖模式

- ❌ 不是生产级多租户 SaaS
- ❌ 非 GPU 本地推理
- ❌ 分轨/重绘/拼接续接（除非上游 API 支持）

---

## 系统要求

- Python 3.10+（支持 3.14）
- ACE-Step 的 API Key
- Node.js 20+（仅运行 Playwright E2E 测试时需要）
- Windows / Linux / macOS

---

## 快速开始

### FastAPI 模式（推荐）

```powershell
# 1. 克隆并安装依赖
git clone https://github.com/yourusername/you2music.git
cd you2music
pip install -r backend/requirements.txt

# 2. 配置 API Key
cp config/providers.local.example.json config/providers.local.json
# 编辑 providers.local.json，填入你的 keys

# 3. 启动
$env:AI_MUSIC_JWT_SECRET = "replace-with-random-secret"
python backend/main.py

# 打开 http://127.0.0.1:8000
```

### stdlib 模式（零依赖，无需 pip）

```powershell
cp config/providers.local.example.json config/providers.local.json
# 同样编辑 providers.local.json
python backend/stdlib_server.py
# 打开 http://127.0.0.1:8000
```

> stdlib 模式不支持登录/注册，UI 自动切换到"本地模式"。

---

## 主要功能

| 功能 | 说明 |
|------|------|
| **Provider** | ACE-Step（acemusic.ai） |
| **多 Key 轮询** | 多个 API Key 自动轮询，429/401/连续失败自动切换 |
| **人声/歌词** | 可开关人声，歌词随 prompt 传入 |
| **延长** | 使用相同 prompt + 更大时长重新生成更长曲目 |
| **API 日志** | 管理后台可查看每次调用的请求/响应/状态/耗时 |
| **配额管理** | 用户每日配额，邀请码注册 |
| **多端同步** | SSE 实时推送，同一账号多端任务状态自动同步 |

---

## 项目结构

```
you2music/
├── backend/
│   ├── main.py              # FastAPI 入口
│   ├── stdlib_server.py     # 零依赖 HTTP 服务器
│   ├── config.py            # 配置加载（env → JSON → 默认值）
│   ├── storage.py           # SQLite 任务存储 + API 日志存储
│   ├── user_store.py        # SQLite 用户/配额/邀请码
│   ├── concurrency.py       # Provider 队列、限流、重试
│   ├── workers.py           # Job 执行 + API 调用日志埋点
│   ├── key_pool.py          # 多 Key 轮询 + 健康追踪
│   ├── providers/           # ACE-Step 客户端
│   ├── static/              # 前端 HTML
│   └── tests/               # pytest 单元 + API 集成测试
├── frontend/
│   └── e2e/                 # Playwright E2E 测试
├── config/
│   └── providers.local.example.json   # 配置示例（勿提交真实 keys）
├── docs/
│   ├── USAGE.md             # 使用指南
│   ├── CONFIG.md            # 配置详解
│   └── ARCH.md              # 架构说明
├── tools/
│   ├── pip_install_backend.ps1        # Python 3.14 pip 修复脚本
│   └── py314_tempfile_fix/             # sitecustomize.py 补丁
└── data/                    # SQLite DB + 生成的音频文件（运行时创建）
```

---

## 测试

### Backend

```powershell
# 安装运行时依赖 + 测试依赖
pip install -r backend/requirements.txt -r backend/requirements-dev.txt

# 全量 backend 测试
python -X utf8 -m pytest -c backend\pytest.ini backend\tests -q

# 仅 API 集成测试
python -X utf8 -m pytest -c backend\pytest.ini backend\tests\test_api -q

# Lint
ruff check .
```

API 测试通过 `backend/tests/test_api/test_env.py` 自动启用隔离环境和 `AI_MUSIC_TEST_MODE=1`，不会依赖本机 `data/` 或真实 ACE-Step API。测试模式下 worker 生成固定短 WAV，音频测试会校验 `RIFF/WAVE` magic bytes。

### 一键全量测试

```powershell
# 后端全量 + ruff + E2E 全量；会安装 Python/npm 依赖与 Playwright 浏览器
.\tools\test_all.ps1

# PR 级快速验证：后端全量 + ruff + E2E smoke
.\tools\test_all.ps1 -Smoke

# 已安装依赖时跳过安装步骤
.\tools\test_all.ps1 -Smoke -SkipInstall -SkipBrowserInstall
```

可选参数：`-SkipBackend`、`-SkipE2E`、`-Ui`、`-E2EPort 8010`、`-E2EWorkers 2`。脚本默认自动选择一个空闲 E2E 端口、禁止复用已有服务，并用 1 个 worker 串行跑 E2E，避免误连本机开发服务器或多个浏览器同时争用同一个 test-mode worker 队列；也会把 npm cache 放到 `.tmp\npm-cache`，避免 Windows 上全局 npm cache 无权限导致安装失败。

### Frontend E2E

```powershell
cd frontend\e2e
npm install
npx playwright install chromium webkit

# Smoke 子集
npm run test:smoke

# 全量 E2E
npm test

# UI 调试
npm run test:ui
```

Playwright 会按 `frontend/e2e/playwright.config.ts` 自动启动后端，并设置独立的临时 `AI_MUSIC_DATA_DIR`、`AI_MUSIC_TEST_MODE=1` 和假 API Key。直接运行 `npm test` 时默认端口是 `8000`，可用 `YOU2MUSIC_E2E_PORT` 覆盖；默认 `YOU2MUSIC_E2E_WORKERS=1` 串行执行；只有显式设置 `YOU2MUSIC_E2E_REUSE_SERVER=1` 时才会复用已有服务。

### CI

- `.github/workflows/ci.yml` 运行 backend tests 与 `ruff check .`。
- `.github/workflows/test.yml` 运行 API integration tests；E2E 由仓库变量 `ENABLE_E2E=1` 启用，PR/push 跑 `@smoke`，定时任务跑全量。

---

## 文档

- [使用指南](docs/USAGE.md)
- [配置说明](docs/CONFIG.md)
- [架构设计](docs/ARCH.md)
- [Contributing](CONTRIBUTING.md)

---

## 许可

MIT License - 详见 [LICENSE](LICENSE)
