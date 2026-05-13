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
│   └── tests/               # pytest 单元测试
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

## 文档

- [使用指南](docs/USAGE.md)
- [配置说明](docs/CONFIG.md)
- [架构设计](docs/ARCH.md)
- [Contributing](CONTRIBUTING.md)

---

## 许可

MIT License - 详见 [LICENSE](LICENSE)
