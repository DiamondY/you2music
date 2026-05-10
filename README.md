# you2music (API + 歌唱)

小范围内部工具，通过 **MiniMax 官方 API** 或 **ACE-Step (acemusic.ai)** 生成音乐（可选人声/歌词），提供简洁的 Web UI 和本地存储。

## 这是什么（不是什么）

- ✅ 目标：小团体使用的「提示词 → 生成 → 试听 → 下载」端到端流程。
- ✅ 支持多候选生成（每个提示词 2–4 种变体）。
- ✅ 支持「延长」（通过更长的时长重新作曲实现；尽力而为，非真正的拼接续接）。
- ✅ 使用云端 API 服务商（默认：MiniMax / ACE-Step），无需 GPU。
- ✅ 支持多 API Key 轮询 + 故障自动切换（支持多账号负载均衡和 Key 限流保护）。
- ✅ 在 SQLite 中保留审计日志（提示词/参数/模型/版本/时间）以便调试。
- ❌ 不是完整的生产级多租户系统（仅基础认证/配额能力，单进程假设）。
- ❌ 「延长/重绘/分轨」除非服务商支持，否则未实现。

## 系统要求

- Windows + PowerShell
- Python 3.10+（支持 3.14）
- MiniMax 或 ACE-Step 的 API Key（至少配置一个）

## 快速开始（无依赖模式，推荐）

此模式仅使用 Python 标准库（无需 `pip install`）。

1) 设置环境变量（PowerShell）：

```powershell
$env:MINIMAX_API_KEY="你的密钥"
# 或者：
$env:ACESTEP_API_KEY="你的密钥"
```

可选：

```powershell
$env:AI_MUSIC_DATA_DIR="C:\Users\Administrator\Documents\Playground\ai-music-tool\data"
$env:AI_MUSIC_OUTPUT_FORMAT="mp3_44100_192"
```

2) 运行：

```powershell
cd C:\Users\Administrator\Documents\Playground\ai-music-tool
python .\backend\stdlib_server.py
```

3) 打开浏览器访问：

- http://127.0.0.1:8000

## 文档

- 使用指南：`docs\USAGE.md`
- 配置说明：`docs\CONFIG.md`
- 架构设计：`docs\ARCH.md`

## FastAPI 模式（推荐）

如果你更喜欢 FastAPI（更好的文档、异步支持），安装依赖后运行 `backend\main.py`：

```powershell
python -m pip install -r .\backend\requirements.txt
$env:AI_MUSIC_JWT_SECRET="随便一段长随机字符串（用于本地 JWT）"
python .\backend\main.py
```

### pip PermissionError 修复方案（Python 3.14）

如果 `pip install` 出现以下错误：

- `Permission denied: ...\\pip-unpack-...\\*.whl.metadata`
- 或创建 venv 时 `ensurepip` 失败

这是因为此环境下 Python 可能创建不可写的临时目录。请使用提供的启动补丁（通过 `PYTHONPATH`）和安装脚本：

```powershell
cd C:\Users\Administrator\Documents\Playground\ai-music-tool
.\tools\pip_install_backend.ps1
```

其内部设置了：

- `PYTHONPATH=...\tools\py314_tempfile_fix`（加载 `sitecustomize.py`）
- `PY_TEMP_BASE=...\ .tmp_python`（项目内的可写临时目录）
- 使用 `--prefer-binary` 和 `--only-binary=pydantic-core,jiter` 安装，避免 Python 3.14 上的 Rust 源码编译

快速验证（可选）：

```powershell
cd C:\Users\Administrator\Documents\Playground\ai-music-tool
$env:PYTHONPATH="$PWD\tools\py314_tempfile_fix"
$env:PY_TEMP_BASE="$PWD\.tmp_python"
python -c "import tempfile, pathlib; d=tempfile.mkdtemp(prefix='pip-'); pathlib.Path(d,'x.txt').write_text('ok',encoding='utf-8'); print('ok', d)"
```

## 关于「歌唱/人声」

本工具提供「人声」开关：

- `人声=开`：提示模型生成带人声的歌曲
- `人声=关`：提示模型生成纯音乐

界面中有「歌词」输入框；对 MiniMax / ACE-Step 会以对应方式传入（或拼接到 prompt），效果会随提示词与模型而变化。

## 关于「延长」

MiniMax / ACE-Step 的「延长」在本项目中采用“重新生成更长版本”的策略：使用相同提示词/参数，将 `duration_sec` 增加后重新生成一个**新的、更长的**曲目（尽力保持连贯性）。

## 文件结构

- `backend\main.py`：FastAPI 应用及路由
- `backend\stdlib_server.py`：无依赖 HTTP 服务器（推荐）
- `backend\providers\minimax.py` / `backend\providers\minimax_stdlib.py`：MiniMax provider
- `backend\providers\acestep.py` / `backend\providers\acestep_stdlib.py`：ACE-Step provider
- `backend\storage.py`：SQLite 任务存储
- `backend\static\index.html`：单页 UI
- `data\`：SQLite 数据库 + 生成的音频文件（首次运行时创建）
