# 测试自动化方案 — you2music

> 修订版 v7，基于 v6 评审意见全面落实（2026-05-14）

---

## 1. 当前测试状态

| 层级 | 现状 | 覆盖率 |
|------|------|--------|
| Backend 单元测试 | pytest（storage, user_store, key_pool, concurrency, acestep） | 仅底层逻辑，无 API 路由层 |
| Backend API 集成测试 | **空白** | 0% |
| Frontend E2E 测试 | **空白** | 0% |
| 前后端契约测试 | **空白** | 0% |

**核心问题**: 前后端通过 REST API 通信，但没有任何测试守护这条链路。UI 大改后无法自动化验证功能正常；后端 API 改动静默破坏前端。

**注意事项**: `pytest` / `pytest-asyncio` 当前仅作为开发环境全局安装存在，**未在 `backend/requirements.txt` 中声明**。需在实施前补充到 `requirements-dev.txt`（见第 7 节）。

---

## 2. 测试分层架构

```
┌──────────────────────────────────────────────┐
│  E2E Tests (Playwright)                      │
│  真实浏览器 + 真实 HTTP 请求                  │
│  验证完整的用户操作链路                       │
├──────────────────────────────────────────────┤
│  API Integration Tests (pytest)              │
│  默认用 FastAPI TestClient；并发/stream 用 httpx + ASGITransport │
│  充当前后端之间的"守护神"                     │
├──────────────────────────────────────────────┤
│  Backend Unit Tests (已有 pytest)            │
│  storage, user_store, key_pool, concurrency   │
└──────────────────────────────────────────────┘
                      ↑
              共享 OpenAPI Schema
              (由后端生成，自动验证)
```

---

## 3. 关键架构约束（修订依据）

> 本节用于解释“为什么计划必须这样写”。同时补充一组 **落地决策点**（必须由维护者确认），避免后续实施时反复返工。

### 3.1 STATE 全局单例的约束

`backend/state.py` 中 `STATE = AppState.create()` 在**模块导入时**即执行，测试无法拦截。`AppState.create()` 在启动时会读取以下输入（其中部分可缺省，但测试必须确保不会误用本机真实数据/密钥）：

- （可选）配置文件 `config/providers.local.json` 或 `config/providers.json`（测试环境**不建议依赖**，优先用 env 覆盖）
- 环境变量：`ACESTEP_API_KEY`、`AI_MUSIC_JWT_SECRET` 等
- 磁盘上的 SQLite 数据库（`data/app.db`、`data/users.db`）
- 磁盘上的音频目录（`data/audio/`）

`deps.py` 中的 `get_current_user` 等依赖**直接引用全局 `STATE`**，非依赖注入模式，无法通过 `app.dependency_overrides` 替换。

**解决方案**：采用**环境变量驱动**（改动最小），在 pytest session 级别通过 `monkeypatch.setenv` 设置测试专用的临时目录和假密钥，使 `AppState.create()` 初始化一个隔离的测试实例。

#### 3.1.1 app fixture 导入时序风险

`app` fixture（`scope="session"`）内部执行 `from main import app as _app`，这会触发整个后端模块链的导入。如果**任何测试文件**在 `conftest.py` 之外还顶层 `import main` 或 `import state`，则 `STATE` 会在 `setup_test_env` fixture 运行之前就被创建，导致使用错误的环境变量。

**防护措施（三选一，推荐组合使用）**：

1. **`test_api/` 目录下添加 `__init__.py`**：确保该目录作为独立 package，pytest 的模块发现机制不会在 conftest 之前导入测试文件
2. **禁止测试文件顶层导入 `main` / `state`**：所有对后端模块的引用必须通过 fixture（如 `app`、`client`）获取，或在测试函数内部延迟导入
3. **提取 `test_env.py` 辅助模块**：将 module-level `os.environ.setdefault` 提取到 `backend/tests/test_api/test_env.py`，在所有测试文件顶部 `import test_env`，确保时序安全

**验收标准**：`pytest -c backend/pytest.ini backend/tests/test_api/ --collect-only` 不触发 `STATE` 创建（可通过在 `state.py` 的 `AppState.create()` 入口添加临时 print 验证）。

### 3.2 Worker 不应真实调外部 API

调用 `/api/generate` 时，job 会被放入 `ProviderQueue`，真实 worker 会尝试连接 ACE-Step API。测试环境必须避免真实 API 调用。

**解决方案**：设置 `ACESTEP_BASE_URL=http://localhost:0`（不存在的地址），worker 连接失败即标记 job 为 failed，不影响测试断言。

#### 补充：成功链路测试策略 — 选定方案 A

仅用 `ACESTEP_BASE_URL=http://localhost:0` 能“止血”（避免误打外部 API），但会导致测试只能覆盖失败路径，难以验证：
- job 最终完成（succeeded）
- 音频结果可播放/可下载
- 前端历史记录/播放器渲染等完整链路

**选定方案：`AI_MUSIC_TEST_MODE=1` Provider Stub**

测试模式下 worker 不发起外部请求，直接产出一个可预测的假结果（写入一段固定的短音频/占位文件），并将 job 标记为 succeeded。

- 优点：API tests 与 E2E 都能覆盖成功链路；整体最稳
- 缺点：需要少量后端代码改造（但可完全隔离在 test mode 分支中）
- 实现方式：在 `_run_job()` 内部（而非 `_job_worker_handler`）增加条件分支，当 `AI_MUSIC_TEST_MODE=1` 时在调用 `ACEStepClient` 之前拦截，跳过外部 API 调用，直接写入固定测试音频文件并将 job 状态设为 succeeded。**注意**：Stub 必须插入 `_run_job()` 而非 `_job_worker_handler`，因为后者包含 rate limiter 获取和 `queued → running` 状态转换逻辑，跳过会导致这些关键路径无法被测试覆盖。

**建议的 Stub 具体约定（确保“成功链路”可测且可复用）**：
- **输出格式**：固定生成 `wav`，文件名使用 `{job_id}.wav`；兼容路由 `/api/audio/{job_id}.mp3` 仍可访问同一 job 的实际输出文件，用于守护历史前端兼容性
- **输出路径**：写入 `AI_MUSIC_DATA_DIR/audio/`（即运行期的 `STATE.audio_dir`），保持与真实流程一致
- **状态与事件**：与真实流程同样写入 `output_path` 并将 job 状态设为 `succeeded`（并发布 SSE 状态变更事件），确保 UI 可用
- **可控时延（可选）**：支持 `AI_MUSIC_TEST_DELAY_MS=200` 等参数，模拟 queued→running→succeeded 的时间窗口（默认可为 0）
- **可控失败（可选）**：支持 `AI_MUSIC_TEST_FORCE_ERROR=1`，强制将本次 job 标记为 failed（用于稳定覆盖 Toast/错误文案/配额回滚等用例）

**验收标准（建议写入 Phase 0 的“验证”项）**：
- 当 `AI_MUSIC_TEST_MODE=1` 时，调用 `/api/generate` 后 job 最终进入 `succeeded`
- `rec.output_path` 指向的文件存在且非空，且可通过 `/api/audio/{job_id}` 正常下载（返回 200）

#### `_run_job()` Test Mode Stub 伪代码

以下是 `backend/workers.py` 中 `_run_job()` 方法的改造参考。Stub **必须**插入 `_run_job()` 开头（在调用 `ACEStepClient` 之前），而不是放在 `_execute_queued_job()` / `_job_worker_handler()` 中：
- rate limiter 获取、排队超时、`queued → running` 状态转换发生在 `_execute_queued_job()`（这些逻辑需要被测试覆盖）
- `_execute_queued_job()` 会通过 `run_with_retry(lambda: _run_job(...))` 进入 `_run_job()`（Stub 放在 `_run_job()` 才能在“保留重试/状态流转覆盖”的前提下，跳过外部 API）

```python
# backend/workers.py — _run_job() 方法改造（示意，接口对齐当前实现）
import os
import asyncio
from pathlib import Path

from state import STATE

async def _run_job(*, job_id: str, prompt: str, params: dict) -> None:
    """Execute a single music generation job. Called by _execute_queued_job via run_with_retry()."""

    # ── Test Mode Stub：跳过外部 API，直接产出可预测的假结果 ──
    if os.environ.get("AI_MUSIC_TEST_MODE") == "1":
        # 可控时延：模拟真实生成耗时（默认 0）
        delay_ms = int(os.environ.get("AI_MUSIC_TEST_DELAY_MS", "0") or "0")
        if delay_ms > 0:
            await asyncio.sleep(delay_ms / 1000.0)

        # 可控失败：强制标记 job 为 failed（用于测试错误路径）
        if os.environ.get("AI_MUSIC_TEST_FORCE_ERROR") == "1":
            STATE.store.set_status(job_id, status="failed", error="test-mode forced error")
            rec = STATE.store.get(job_id)
            await _publish_job_status(
                user_id=(rec.user_id if rec else None),
                job_id=job_id,
                status="failed",
                provider="acestep",
                error="test-mode forced error",
            )
            return

        # 生成固定测试音频（WAV，避免引入 MP3 编码器依赖）
        # 约定：test mode 直接在内存中生成 250ms 16-bit PCM silence WAV，
        # 测试通过 RIFF/WAVE magic bytes 验证有效性。
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(8000)
            wf.writeframes(b"\x00\x00" * int(8000 * 0.25))
        out_bytes = buf.getvalue()

        STATE.audio_dir.mkdir(parents=True, exist_ok=True)
        out_path = STATE.audio_dir / f"{job_id}.wav"
        out_path.write_bytes(out_bytes)

        # 更新 job 状态为 succeeded（与真实流程一致）+ 发布 SSE 事件（保持 UI 链路可测）
        STATE.store.set_status(job_id, status="succeeded", output_path=str(out_path))
        rec = STATE.store.get(job_id)
        await _publish_job_status(
            user_id=(rec.user_id if rec else None),
            job_id=job_id,
            status="succeeded",
            provider="acestep",
        )
        return

    # ── 正常流程：调用 ACEStepClient（原有逻辑保持不变） ──
    ...
```

**Stub 设计要点**：
- **插桩位置**：`_run_job()` 开头，`ACEStepClient` 调用之前
- **不跳过 `_execute_queued_job`**：rate limiter 获取、排队超时、`queued → running` 状态转换都在这里完成；Stub 放在 `_run_job` 才能保留这些关键路径的测试覆盖
- **输出格式**：固定 `wav`，文件名 `{job_id}.wav`；测试同时覆盖 `/api/audio/{job_id}` 与 `/api/audio/{job_id}.mp3` 兼容路由，二者都通过 RIFF/WAVE magic bytes 验证
- **输出路径**：写入 `STATE.audio_dir`，与真实流程一致
- **SSE 事件**：`running` 由 `_execute_queued_job` 发布；Stub 分支需要像正常成功路径一样发布 `succeeded/failed`，否则前端 SSE 链路无法覆盖
- **可控参数**：`AI_MUSIC_TEST_DELAY_MS`（时延）、`AI_MUSIC_TEST_FORCE_ERROR`（强制失败）

> ⚠️ **实施前必须验证**：伪代码中调用的 `_publish_job_status(user_id=..., job_id=..., status=..., provider=..., error=...)` 签名基于推测。实施前需 `rg -n "def _publish_job_status" backend/workers.py` 确认实际参数列表，若不匹配需调整伪代码。同样，`STATE.store.set_status(job_id, status=..., output_path=...)` 的参数顺序也需与实际 `JobStore.set_status()` 签名对齐。

> `ACESTEP_BASE_URL=http://localhost:0` 仍保留作为兜底，防止配置失误导致误打真实 API。

### 3.3 前端双布局模型

项目使用**独立 DOM 树**：`#pcLayout`（桌面）vs `#mobilePanels`（移动端），非纯 CSS 响应式。切换依赖 `window.innerWidth >= 1100`。

每个核心交互测试需要覆盖两个 viewport：
- 桌面：1280×800（`#prompt`、`#generateBtn`）
- 移动：375×812（`#promptMobile`、`#generateBtnMobile`）

### 3.4 SSE 长连接

`/api/events` SSE 流是多标签/多设备同步的核心。Playwright 测试 SSE 时需要处理：连接建立、自动重连（1.5s）、连接终止。

> **测试注意**：SSE 属于无限流。如果在 API tests（TestClient）里验证 SSE，必须用带超时的 stream 读取，并在拿到第一条 `event: hello/ping` 后立即主动断开，避免 CI 卡死（hang）。

> **v6 修订**：SSE 测试**默认采用方案 B（`httpx.AsyncClient` + `ASGITransport`）**。原因：`TestClient.stream()` + `iter_lines()` 对 SSE 的兼容性未验证——SSE 协议使用 `\n\n` 分隔事件，而 `iter_lines()` 默认按 `\n` 分割，会导致一个 SSE 事件被拆成多行，`"hello" in line` 的判断可能匹配到事件的中间行而非 `data:` 字段。方案 B 使用 `aiter_lines()` + 显式 `ASGITransport(app=app)` 能确保不发起真实网络请求，且异步流解析更可靠。

### 3.5 E2E 无法 mock 后端

Playwright 的 `page.route()` 可以拦截和伪造响应（类似 Proxy），但需要**真实后端服务器运行**。不能像 Cypress 那样完全隔离。

---

## 4. Layer 1 — Backend API Integration Tests

### 目标
使用 `pytest` + `FastAPI TestClient` 直接测试所有 API 端点，验证响应格式、状态码、错误文案。

### 测试文件结构
```
backend/tests/
├── conftest.py              # [已有] 现有 DB fixture（tmp_db_path, job_store, user_store），保持不变
├── test_acestep.py          # [已有]
├── test_key_pool.py         # [已有]
├── test_user_store.py       # [已有]
├── test_concurrency.py      # [已有]
├── test_storage.py          # [已有]
├── test_workers.py         # [新增] worker 逻辑单元测试：job 状态流、重试、配额退还
└── test_api/
    ├── conftest.py          # [新增] session-level env setup, app fixture, test DB, auth helper（扩展根 conftest）
    ├── test_auth.py         # register / login / me / me(update) / password
    ├── test_jobs.py         # generate / generate_many / generate_store / extend / cancel / delete / batch_delete / inpaint / stems
    ├── test_history.py      # jobs/recent / jobs/history / jobs/{id} / jobs (list)
    ├── test_community.py    # publish / unpublish / community / community audio
    ├── test_audio.py        # [新增] audio/{id} / audio/{id}.mp3 / community audio — 权限与路径安全
    ├── test_upload.py       # [新增] uploads/audio — 文件类型校验与大小限制
    ├── test_providers.py    # [新增] providers list / random_sample
    ├── test_quota.py        # quota enforcement, 429, refund on failure
    ├── test_admin.py        # admin-only endpoints, role enforcement
    ├── test_concurrency.py  # 并发 generate quota 一致性（独立用户）
    ├── test_validation.py   # 边界值与安全回归
    ├── test_contract.py     # OpenAPI 快照 + Level 2 响应体契约
    └── test_sse.py          # /api/events SSE stream（基础连接、事件接收、多连接）
```

### SSE 测试策略

SSE 是无限流，使用 `TestClient`（基于 `httpx`）测试时需要特别注意：

1. **必须用 stream 上下文管理器**读取 SSE，读取到预期事件后立即断开，避免测试卡死
2. **默认采用方案 B（AsyncClient + ASGITransport）**：`TestClient.stream()` + `iter_lines()` 对 SSE 兼容性未验证——SSE 使用 `\n\n` 分隔事件，`iter_lines()` 按 `\n` 分割会导致事件被拆行，匹配逻辑失效
3. **超时保护**：所有 SSE 测试必须设置读取超时，防止无限等待

```python
# test_sse.py — 方案 B：AsyncClient + ASGITransport（推荐，v6 默认方案）
import pytest
import httpx

@pytest.mark.asyncio
async def test_sse_requires_auth(app):
    """未认证请求 SSE 应返回 401/403。"""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
        resp = await ac.get("/api/events")
        assert resp.status_code in (401, 403)

@pytest.mark.asyncio
async def test_sse_connect_and_hello(app, auth_headers):
    """认证后连接 SSE，应收到 hello 事件。"""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
        async with ac.stream("GET", "/api/events", headers=auth_headers) as resp:
            assert resp.status_code == 200
            # 使用 aiter_lines() 解析 SSE 事件
            async for line in resp.aiter_lines():
                if line.strip() == "event: hello":
                    return
            raise AssertionError("Did not receive SSE event: hello")
```

**方案 B 注意事项**：
- **必须使用 `ASGITransport(app=app)`**，否则 `base_url="http://testserver"` 只是一个普通 URL，会发起真实网络请求（会导致测试在 CI 或离线环境失败）
- `base_url="http://testserver"` 只用于拼接相对路径（`/api/...`），与是否走 ASGI transport 无关
- 需要在 `backend/requirements-dev.txt` 中确认 `httpx` 版本支持 `ASGITransport`（`httpx>=0.25`）
- **SSE 事件解析**：`aiter_lines()` 按 `\n` 分割，SSE 的 `event:` / `data:` 字段会作为独立行返回。匹配时应检查行是否以 `event: hello` 或 `data:` 开头，而非简单的 `"hello" in line`

#### SSE 事件解析 Helper（推荐复用）

SSE 协议使用 `\n\n` 分隔事件，`aiter_lines()` 按 `\n` 分割会产生空行作为事件边界。以下 helper 封装了完整的事件读取逻辑，建议以 **fixture** 形式放在 `backend/tests/test_api/conftest.py` 中：这样 SSE 测试文件**无需 import**，只要在测试函数参数中声明 `read_sse_event` 即可复用（pytest 会自动注入 fixture）。

```python
import asyncio
from typing import AsyncIterator, Awaitable, Callable

import pytest

@pytest.fixture
def read_sse_event() -> Callable[[AsyncIterator[str]], Awaitable[dict]]:
    """SSE 事件读取器（factory fixture）。

    注意：`conftest.py` 中定义的普通函数不会自动出现在测试模块命名空间里；
    用 fixture 返回函数，可以让所有 test_* 文件通过参数注入直接复用（无需 import）。
    """

    async def _read_sse_event(aiter: AsyncIterator[str], *, timeout_s: float = 5.0) -> dict:
        """从 SSE 流中读取一个完整的事件（event + data，以空行结束）。

        Returns:
            {"event": "hello", "data": "{...}"} 或 {"data": "..."} 等。
            若超时未收到完整事件，返回空 dict。
        """
        event: dict = {}

        async def _read_one() -> dict:
            async for line in aiter:
                line = line.strip()
                if line == "":
                    # 空行 = 事件边界，返回已收集的事件
                    if event:
                        return event
                    continue
                if line.startswith("event:"):
                    event["event"] = line[6:].strip()
                elif line.startswith("data:"):
                    # data 字段可能有多行，追加而非覆盖
                    event.setdefault("data", "")
                    event["data"] += line[5:].strip()
            return event

        try:
            # 使用 wait_for 保持 Python 3.10+ 兼容（asyncio.timeout 需要 3.11+）
            return await asyncio.wait_for(_read_one(), timeout=timeout_s)
        except asyncio.TimeoutError:
            return {}

    return _read_sse_event
```

**使用示例**（替换上文 `test_sse_connect_and_hello` 中的逐行匹配）：

```python
@pytest.mark.asyncio
async def test_sse_connect_and_hello(app, auth_headers, read_sse_event):
    """认证后连接 SSE，应收到 hello 事件。"""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
        async with ac.stream("GET", "/api/events", headers=auth_headers) as resp:
            assert resp.status_code == 200
            event = await read_sse_event(resp.aiter_lines(), timeout_s=5.0)
            assert event.get("event") == "hello"
```

> 该 helper 同样适用于后续 `test_sse.py` 中更复杂的事件接收测试（job_updated、job_progress 等），避免每个测试重复编写 SSE 解析逻辑。

<details>
<summary>方案 A（备选，仅在方案 B 不兼容时使用）</summary>

```python
# test_sse.py — 方案 A：同步 TestClient（备选，兼容性未验证）
def test_sse_requires_auth(client):
    """未认证请求 SSE 应返回 401/403。"""
    resp = client.get("/api/events")
    assert resp.status_code in (401, 403)

def test_sse_connect_and_hello(client, auth_headers):
    """认证后连接 SSE，应收到 hello 事件，然后立即断开。"""
    with client.stream("GET", "/api/events", headers=auth_headers) as resp:
        assert resp.status_code == 200
        assert resp.headers.get("content-type", "").startswith("text/event-stream")
        # 读取事件行，直到收到 hello
        for line in resp.iter_lines():
            if "hello" in line:
                break
    # with 块退出时自动断开连接
```

> ⚠️ **方案 A 兼容性风险**：`TestClient.stream()` + `iter_lines()` 对 SSE 的兼容性**未经验 证**。`iter_lines()` 默认按 `\n` 分割，而 SSE 使用 `\n\n` 分隔事件，会导致一个 SSE 事件被拆成多行，匹配逻辑可能失效。**不建议作为首选方案**。

</details>

### conftest.py 架构：test_env.py + 根 conftest + test_api/conftest

**`backend/tests/test_api/test_env.py`（新增，v6）**：提取 module-level 环境变量设置到独立模块，确保时序安全。所有测试文件必须在顶层导入此模块。

```python
# backend/tests/test_api/test_env.py
"""必须在任何后端模块导入之前执行。
所有 test_api/ 下的测试文件应在顶层 import 此模块。
"""
import os
import tempfile
from pathlib import Path

# ── 测试环境变量常量（单一来源，conftest.py 通过 import TEST_ENV 复用）──
TEST_ENV: dict[str, str] = {
    "AI_MUSIC_JWT_SECRET": "test-jwt-secret-for-testing-only",
    "AI_MUSIC_ADMIN_USERNAME": "admin",
    "AI_MUSIC_ADMIN_PASSWORD": "adminpw",
    "AI_MUSIC_DEFAULT_DAILY_QUOTA": "999",
    "ACESTEP_API_KEY": "test-key",
    "ACESTEP_BASE_URL": "http://localhost:0",
    "AI_MUSIC_TEST_MODE": "1",
}

# 第一层防护：模块导入时立即设置，任何间接 import main 的代码都受保护。
#    setdefault 确保仅在未设置时才覆盖，允许 session fixture 第二层覆盖。
os.environ.setdefault(
    "AI_MUSIC_DATA_DIR",
    str(Path(tempfile.gettempdir()) / "you2music_test_default"),
)
for _k, _v in TEST_ENV.items():
    os.environ.setdefault(_k, _v)
```

**根 `backend/tests/conftest.py`（已有）**：提供 DB 级 fixture（`tmp_db_path`、`job_store`、`user_store`），供现有单元测试使用，保持不变。

**`backend/tests/test_api/conftest.py`（新增）**：扩展根 conftest，添加 API 测试所需的 fixture。

> **v6 修订**：原方案将 module-level `os.environ.setdefault` 直接写在 `test_api/conftest.py` 中。但 `conftest.py` 的加载时机受 pytest 模块发现机制影响，若测试文件在 conftest 之前被导入（例如通过 `conftest.py` 之外的 import 链），环境变量可能未就绪。因此 v6 将环境变量设置提取到独立的 `test_env.py`，并在 conftest 中通过 `import test_env` 引用，确保时序确定性。

```python
# backend/tests/test_api/conftest.py
import os
import tempfile
from pathlib import Path

# 确保 test_env.py 已执行（防御性导入，即使 pytest 已加载 conftest 也无副作用）
# 同时复用 TEST_ENV 常量，避免与 test_env.py 中的 env 列表重复维护
import test_env  # noqa: F401
from test_env import TEST_ENV

import pytest
from fastapi.testclient import TestClient

@pytest.fixture(scope="session", autouse=True)
def setup_test_env():
    """Set env vars before STATE is created at module import time."""
    # 使用 TemporaryDirectory 确保 session 结束后自动清理（Windows 下忽略 WAL 锁清理错误）。
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        tmp = Path(td)
        # 从 TEST_ENV 常量统一设置，仅覆盖 DATA_DIR 为 session 级临时目录
        os.environ.update(TEST_ENV)
        os.environ["AI_MUSIC_DATA_DIR"] = str(tmp)
        yield

@pytest.fixture(scope="session")
def app():
    """Create FastAPI app with test environment."""
    assert os.environ.get("AI_MUSIC_TEST_MODE") == "1", (
        "Test env not initialized — AI_MUSIC_TEST_MODE must be '1'. "
        "Check that test_env.py or setup_test_env ran first."
    )
    assert os.environ.get("AI_MUSIC_JWT_SECRET"), "AI_MUSIC_JWT_SECRET not set"
    assert os.environ.get("AI_MUSIC_DATA_DIR"), "AI_MUSIC_DATA_DIR not set"
    from main import app as _app
    return _app

@pytest.fixture(scope="session")
def client(app):
    """TestClient for API integration tests."""
    return TestClient(app)

@pytest.fixture(scope="session")
def test_id():
    """Session 级唯一标识，用于关联所有测试用户名，方便日志追踪和调试。"""
    import uuid
    return uuid.uuid4().hex[:8]

@pytest.fixture(autouse=True)
def ensure_admin(client):
    """确保 admin 用户存在，供 auth_headers 等 fixture 使用。

    db_clean 会清空 users 表（保留 admin），但如果 admin 创建逻辑依赖
    应用启动时的初始化（而非显式 API 调用），此 fixture 提供额外保障。
    """
    # 尝试登录 admin，若失败则说明 admin 不存在或密码不对
    resp = client.post("/api/auth/login", json={
        "username": os.environ.get("AI_MUSIC_ADMIN_USERNAME", "admin"),
        "password": os.environ.get("AI_MUSIC_ADMIN_PASSWORD", "adminpw"),
    })
    if resp.status_code != 200:
        # admin 不存在，可能需要通过应用初始化逻辑创建
        # 此处记录警告，具体创建方式取决于后端实现
        import warnings
        warnings.warn(
            f"Admin login failed ({resp.status_code}): {resp.text}. "
            "Tests depending on admin auth_headers will fail."
        )

@pytest.fixture
def auth_headers(client, test_id):
    """Register a test user and return Authorization headers."""
    # 先通过 admin 创建 invite code，再注册
    admin_username = os.environ.get("AI_MUSIC_ADMIN_USERNAME", "admin")
    admin_password = os.environ.get("AI_MUSIC_ADMIN_PASSWORD", "adminpw")
    resp = client.post("/api/auth/login", json={"username": admin_username, "password": admin_password})
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    admin_token = resp.json()["token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    # 创建 invite code（假设 admin 端点可用）
    invite_resp = client.post("/api/admin/invite-codes", headers=admin_headers)
    assert invite_resp.status_code == 200, f"Create invite code failed: {invite_resp.text}"
    invite_code = invite_resp.json()["invite_code"]["code"]
    # 注册测试用户（用户名包含 session 级 test_id，方便关联日志）
    import uuid
    username = f"testuser_{test_id}_{uuid.uuid4().hex[:6]}"
    reg_resp = client.post("/api/auth/register", json={
        "username": username,
        "password": "testpass123",
        "invite_code": invite_code,
    })
    assert reg_resp.status_code == 200, f"Register failed: {reg_resp.text}"
    token = reg_resp.json()["token"]
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture(autouse=True)
def db_clean():
    """前置清理（before each test）：清空关键表，防止测试间互相污染。

    本项目有两套 DB：app.db 与 users.db。
    - app.db: jobs / audio_uploads / api_logs
    - users.db: users / invite_codes / user_quotas

    ✅ v6 要求（Phase 0 首个 PR 必须落地）：
    - 必须使用 Store 层的 `clear_for_tests()`（内部加锁 + DELETE + commit），
      避免测试直接依赖 `_lock` / `_connect()` 等内部实现细节。
    - ❌ 不再允许临时使用 `_connect()` + DELETE — 此方案已从 Phase 0 scope 中移除。
    """
    from state import STATE

    # --- app.db 清理 ---
    STATE.store.clear_for_tests()

    # --- users.db 清理（保留 admin 用户，后续 fixture 依赖 admin 登录）---
    STATE.user_store.clear_for_tests(exclude_admin=True)

    yield
```

关键点：
1. **`test_env.py` 独立模块**：将 module-level `os.environ.setdefault` 提取到 `test_env.py`，所有测试文件顶层 `import test_env`，确保时序确定性（v6 新增）
2. **两层防护**：（a）`test_env.py` 的 setdefault 在任何 import 前生效；（b）session fixture 动态覆盖默认值
3. **环境变量单一来源**：`test_env.py` 导出 `TEST_ENV` 常量字典，`conftest.py` 通过 `from test_env import TEST_ENV` + `os.environ.update(TEST_ENV)` 复用，避免维护两份相同的 env 列表导致漂移
4. **不建议依赖本地 `config/providers.local.json`**：测试应通过 env 明确指定 `ACESTEP_API_KEY` / `AI_MUSIC_JWT_SECRET` 等，避免误用本机配置
5. `auth_headers` fixture 自动处理注册流程，每条测试用例都获得一个已认证的用户（用户名建议随机化，避免清理失败导致冲突）
6. **`ensure_admin` fixture（v6 新增）**：每条测试前验证 admin 用户可登录，若失败则发出警告，避免 `auth_headers` 中 admin 登录失败导致的级联错误难以定位
7. **`db_clean` 使用 `clear_for_tests()`（v6 强制）**：不再允许临时方案 `_connect()` + DELETE；Phase 0 首个 PR 必须实现 `clear_for_tests()` 方法
8. **运行入口固定**：建议统一从仓库根目录运行测试（例如 `python -m pytest -c backend/pytest.ini backend/tests/test_api/`）。若遇到 `ModuleNotFoundError: test_env`，通常是运行目录不一致或 pytest import-mode 被修改导致，需要按本文档的“防护措施”与导入路径约定调整。

### 数据隔离与清理策略

由于 `STATE` 在 import 时创建，**整个 pytest session 共享同一个 data_dir（含 app.db + users.db）**，无法在运行时重建 STATE。因此实际隔离粒度是**表级别清理**，而非 DB 级隔离。

**采用方案：Session 级 data_dir + Function 级表清理（两套 DB）**

- `setup_test_env()` 负责把 `AI_MUSIC_DATA_DIR` 指向临时目录，保证与本地数据完全隔离。
- **不可在测试中重启或重建 STATE** — 整个 session 使用同一个实例。
- 每条测试用例（function）执行前清空关键表（覆盖 app.db 与 users.db），确保互不影响。
- **前提条件**：必须在 Phase 0 首个 PR 中实现 `clear_for_tests()` 方法（v6 强制要求）。

**稳定性约束（避免 flaky）**：
- **任何触发 job 创建的测试用例，必须等待 job 进入终态（`succeeded` / `failed`）后再结束**。否则后台 worker/队列可能在下一条测试开始后仍在更新 DB / 推送 SSE，导致跨用例干扰。
- 推荐在工厂函数中提供 `wait_job()`（见第 10 节“测试数据工厂”），并在所有 job 相关测试中统一使用。

**清理范围（按 DB 分组）**：
- `app.db`：`api_logs`、`audio_uploads`、`jobs`
- `users.db`：`user_quotas`、`invite_codes`、`users`（保留 admin）

**前提条件**：`clear_for_tests()` 方法必须在 Phase 0 首个 PR 中实现（v6 强制要求，不再允许临时方案）。

#### `clear_for_tests()` 伪代码

以下是 `JobStore` 和 `UserStore` 中 `clear_for_tests()` 方法的实现参考。方法内部必须加锁，避免与并发 worker 产生竞态：

```python
# backend/storage.py — JobStore 新增方法
def clear_for_tests(self) -> None:
    """清空 jobs / api_logs / audio_uploads 表（仅供测试环境使用）。"""
    with self._lock:
        conn = self._connect()
        try:
            conn.execute("DELETE FROM api_logs")
            conn.execute("DELETE FROM audio_uploads")
            conn.execute("DELETE FROM jobs")
            conn.commit()
        finally:
            conn.close()

# backend/user_store.py — UserStore 新增方法
def clear_for_tests(self, *, exclude_admin: bool = False) -> None:
    """清空 user_quotas / invite_codes / users 表（仅供测试环境使用）。

    Args:
        exclude_admin: 若为 True，保留 role='admin' 的用户记录。
    """
    with self._lock:
        conn = self._connect()
        try:
            conn.execute("DELETE FROM user_quotas")
            conn.execute("DELETE FROM invite_codes")
            if exclude_admin:
                conn.execute("DELETE FROM users WHERE role != 'admin'")
            else:
                conn.execute("DELETE FROM users")
            conn.commit()
        finally:
            conn.close()
```

**实现要点**：
- 必须在 `with self._lock:` 内执行，避免与 worker 并发写入竞态
- 使用 `self._connect()` 获取连接，与现有代码风格一致
- `exclude_admin` 参数供 `db_clean` fixture 使用，保留 admin 用户以确保 `auth_headers` fixture 可用
- 方法名和签名需与 `db_clean` fixture 中的调用方式对齐：`STATE.store.clear_for_tests()` / `STATE.user_store.clear_for_tests(exclude_admin=True)`

> 备选：如果后续引入”可重建 STATE 的 app fixture”，可进一步升级为”每个 test module 独立 data_dir”，但作为 Phase 0/1 的前置并不必要。

### 重点覆盖场景（来自 prd.md 审查发现）

| 场景 | 验证点 |
|------|--------|
| 正确注册流程 | 201, 返回 token + user, invite code 标记已用 |
| 错误注册 | 409 用户名重复, 400 无效邀请码, 400/409 邀请码已用 |
| 登录 | 401 错误密码, 401 不存在用户, 403 账户禁用 |
| JWT 保护 | 所有 `/api/*` 端点无 token → 401 |
| 错误消息文案 | 401/403/429/500 响应的 `detail` 字段包含**具体错误描述**（非空、非通用文本） |
| generate 成功 | 200, job_id 存在, quota -1 |
| generate 失败配额退还 | job 创建失败时 quota 回滚 |
| generate_many 部分失败 | 未提交的 job 对应配额退还 |
| 公开音频 / 私有音频 | 403 无 token, 200 正确 token |
| quota exhausted | 429 且不创建 job，**detail 包含"配额"关键词** |
| admin 权限 | non-admin → 403 |
| admin 端点明细 | 见下方 admin 测试矩阵 |
| B1: asyncio.create_task 在同步路由中 | 调用 `/api/jobs/{id}/publish` 不崩溃 |
| B3: Quota 消耗无事务回滚 | generate_many 途中失败时，已提交的 job 数对应配额正确扣减 |
| B2: output_path 路径穿越 | 构造恶意 job_id 请求音频，验证 403/404 而非泄露文件 |
| B5: _serialize_job JSON 解析失败 | 插入损坏 JSON 到 jobs 表，验证返回错误而非 500 |
| B6: share_permission 未强制执行 | "仅试听"权限音频验证不可直接下载原始文件 |
| 音频文件有效性 | test_mode 下生成的音频文件是有效 WAV（检查 magic bytes：`RIFF` + `WAVE`），而非空文件或随机数据 |
| 并发 quota 一致性 | 并发 generate 请求后 quota 扣减总数 = 请求数 |
| 边界值：用户名/密码长度 | 超长输入被正确拒绝 |
| 边界值：prompt 最大长度 | 超长 prompt 被正确截断或拒绝 |
| 边界值：invite code 格式 | 无效格式被正确拒绝 |
| 边界值：quota 0/1/最大值 | 边界处行为正确 |

### Admin 测试矩阵

| 端点 | 操作 | admin | non-admin | 未认证 |
|------|------|-------|-----------|--------|
| `GET /api/admin/users` | 用户列表 | 200 | 403 | 401 |
| `PATCH /api/admin/users/{id}` | 修改用户（禁用/配额） | 200 | 403 | 401 |
| `DELETE /api/admin/users/{id}` | 删除用户 | 200 | 403 | 401 |
| `POST /api/admin/invite-codes` | 创建邀请码 | 200 | 403 | 401 |
| `GET /api/admin/config` | 读取配置 | 200 | 403 | 401 |
| `PUT /api/admin/config` | 更新配置 | 200 | 403 | 401 |
| `GET /api/admin/stats` | 系统统计 | 200 | 403 | 401 |

> **B14 关联**：`PUT /api/admin/config` 需要额外测试 — 注入非法 key（如 `malicious_key`）应被拒绝或忽略（schema 校验）。

### 技术选型
- `pytest` + `pytest-asyncio`（已有）
- `FastAPI TestClient` — 同步测试，无需启动真实服务器
- 使用 session 级隔离 `AI_MUSIC_DATA_DIR`（自动创建独立 app.db/users.db），并在 function 级清表避免互相污染
- `ACESTEP_BASE_URL=http://localhost:0` 防止 worker 真实调用外部 API

---

## 5. Layer 2 — E2E Tests (Playwright)

### 目标
用真实浏览器运行完整的用户操作链路，验证 UI 逻辑在各种操作序列后都正常。需要**真实后端服务器运行**。

> **重要前提**：E2E 测试使用 `AI_MUSIC_TEST_MODE=1` 后端（CI 配置中已设置），验证的是**前端 UI 链路**（交互、状态流转、错误处理、布局切换），而非真实的音乐生成。生成结果由 Provider Stub 产出固定假音频，确保链路可预测。

### 测试文件结构

> **v6 命名规范**：E2E 测试文件统一使用 `*.spec.ts`（不加 `test_` 前缀），与 Playwright 社区惯例一致。Python 测试文件保持 `test_*.py` 不变。

```
frontend/e2e/
├── playwright.config.ts   # baseURL, dual viewport projects, failure strategy
├── conftest.ts            # test user factory via API, cleanup
├── auth/
│   ├── register.spec.ts
│   └── login.spec.ts
├── create/
│   ├── generate.spec.ts
│   ├── generate_quota_exhausted.spec.ts
│   └── generate_error.spec.ts      # 使用 page.route() mock 错误
├── history/
│   └── history.spec.ts
├── community/
│   └── community.spec.ts
├── mobile/
│   ├── mobile_layout.spec.ts       # 移动端独立 DOM 测试
│   └── mobile_generate.spec.ts
├── sse/
│   └── sse_reconnect.spec.ts       # SSE 断线重连 + pollTimer 无重复调用
└── admin/
    └── admin.spec.ts
```

### Dual Viewport Projects 配置

```typescript
// playwright.config.ts
import { defineConfig, devices } from '@playwright/test';
import path from 'path';

export default defineConfig({
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile', use: { ...devices['iPhone 13'] } },
  ],
  // 失败时自动截图 + 保留视频，便于调试
  use: {
    baseURL: 'http://127.0.0.1:8000',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    trace: 'on-first-retry',
  },
  // E2E 测试需要真实后端，通过 env 指定
  webServer: {
    command: 'python backend/main.py',
    // 使用 path.resolve 确保 Windows / Linux 都可用，
    // 避免相对路径 '../..' 在不同平台或 IDE 工作目录下解析不一致。
    cwd: path.resolve(__dirname, '../..'),
    url: 'http://127.0.0.1:8000/',
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
    env: {
      // 用相对路径，确保 Windows / Linux 都可用（cwd 已切到仓库根目录）
      AI_MUSIC_DATA_DIR: '.tmp/you2music_e2e',
      AI_MUSIC_JWT_SECRET: 'e2e-test-secret',
      AI_MUSIC_ADMIN_USERNAME: 'admin',
      AI_MUSIC_ADMIN_PASSWORD: 'adminpw',
      AI_MUSIC_DEFAULT_DAILY_QUOTA: '999',  // v6: 与 API 测试保持一致，避免配额耗尽
      ACESTEP_API_KEY: 'fake-key',
      ACESTEP_BASE_URL: 'http://localhost:0',
      AI_MUSIC_TEST_MODE: '1',
    },
  },
});
```

测试文件中通过 `testInfo.project.name` 区分选择器：

```typescript
const promptInput = testInfo.project.name === 'mobile' ? '#promptMobile' : '#prompt';
```

### 错误 mock 策略

使用 `page.route()` 拦截特定 API 响应，**需要真实后端服务器运行**。`page.route()` 拦截的是**浏览器侧的网络请求**（类似 Proxy），后端不会收到被拦截的请求。

**使用边界与注意事项**：
- mock 测试应**独立于正常流程测试** — 同一个 test 中不应混用 mock 和真实请求
- 若同一 test 中需要先 mock 后恢复，使用 `page.unroute()` 解除拦截
- mock 只验证**前端对特定响应的处理行为**（Toast 显示、状态跳转等），不验证后端逻辑

```typescript
// 示例：mock 配额用尽（独立 test，不与正常流程混用）
test('配额用尽时显示提示 @smoke', async ({ page }) => {
  await page.route('**/api/generate', async route => {
    await route.fulfill({
      status: 429,
      contentType: 'application/json',
      body: JSON.stringify({ detail: '今日配额已用完' }),
    });
  });
  // ... 触发生成，验证 Toast 显示 "今日配额已用完"
});

// 示例：同一 test 中先 mock 后恢复
test('错误后恢复正常生成', async ({ page }) => {
  // 先 mock 一次错误
  await page.route('**/api/generate', async route => {
    await route.fulfill({ status: 500, body: JSON.stringify({ detail: '服务器错误' }) });
  }, { times: 1 });  // 只拦截一次
  // ... 触发生成，验证错误提示
  // ... 再次触发生成，这次走真实后端
});
```

### 重点覆盖场景（来自 prd.md 审查发现）

| 场景 | 验证行为 |
|------|--------|
| 正常生成流程 | 输入 prompt → 点生成 → 显示 job_id → 轮询状态 → 播放音频 |
| 配额用尽 | `page.route()` mock 429 → 显示 quota exhausted 提示，**验证 Toast 文案包含"配额"关键词**（🗳 依赖 F3） |
| 移动端布局 | viewport 切换后 #mobilePanels 显示，#pcLayout 隐藏；create form 可交互 |
| Toast 错误提示 | 后端返回错误时 Toast 正确显示且不被 sticky player 遮挡（F3）（🗳 依赖 F3 修复） |
| 错误消息文案 | 后端返回 401/403/429/500 时，前端 Toast **显示后端 detail 字段内容**，而非通用错误文本（🗳 依赖 F3） |
| 401 处理 | JWT 过期后调用 `/api/auth/me` 返回 401 → 清 session → 显示登录页（F13） |
| Enter 提交 | prompt 输入框按 Enter → 触发生成 |
| 清除 prompt | 清除按钮重置输入框 |
| F4: viewport resize | 切换 viewport 后历史列表正常渲染（桌面/移动端都测试） |
| SSE 自动重连 | 断开 SSE 连接后，验证 1.5s 内自动重连；重连后能收到新的 job 状态事件 |
| F11: pollTimer vs SSE | 生成后验证无重复 API 调用（通过 `page.on('request')` 监控请求数量） |

### 技术选型
- **Playwright**（功能最强，支持 Chromium/WebKit/Firefox，支持 mobile viewport）
- **TypeScript**（可选，纯 JS 也可以）
- 每条测试在独立用户数据下运行（通过 invite code 动态创建）
- 失败时自动截图 + 控制台日志

---

## 6. Layer 3 — OpenAPI Contract Tests

### 目标
利用 FastAPI 自带 OpenAPI schema 作为天然契约，避免手写 Pydantic schemas 的双重维护成本。

### Level 1（优先落地）：OpenAPI Schema 快照

测试内容：对 `app.openapi()` 的输出做快照保存；每次变更都要求人工 review（PR diff 清晰可见）。

```python
# backend/tests/test_api/test_contract.py
import json
from pathlib import Path

SNAPSHOTS_DIR = Path(__file__).parent / "snapshots"

def test_openapi_schema_snapshot(client, app):
    """OpenAPI schema must not change without explicit review."""
    schema = app.openapi()
    actual = json.dumps(schema, sort_keys=True, indent=2)

    snapshot_path = SNAPSHOTS_DIR / "openapi.json"
    if snapshot_path.exists():
        expected = snapshot_path.read_text(encoding="utf-8")
        if actual != expected:
            # 写出实际 schema 以便 diff
            (SNAPSHOTS_DIR / "openapi_actual.json").write_text(actual, encoding="utf-8")
            assert False, (
                "OpenAPI schema changed! Review diff between openapi.json and openapi_actual.json. "
                "If intentional, update the snapshot. "
                "Linux/macOS: cp openapi_actual.json openapi.json ; "
                "PowerShell: Copy-Item openapi_actual.json openapi.json -Force"
            )
    else:
        # 首次运行：创建快照
        SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(actual, encoding="utf-8")

def test_all_endpoints_have_response_schemas(client, app):
    """Every API endpoint must declare at least one response schema."""
    schema = app.openapi()
    missing = []
    for path, methods in schema["paths"].items():
        for method, details in methods.items():
            if method.upper() not in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                continue
            if "responses" not in details:
                missing.append(f"{method.upper()} {path}")
                continue
            # 至少有一个非 default 的响应码声明了 content
            has_content = any(
                "content" in resp
                for code, resp in details["responses"].items()
                if code != "default"
            )
            if not has_content:
                missing.append(f"{method.upper()} {path} (no content schema)")
    assert not missing, f"Endpoints missing response schemas: {missing}"
```

- 优点：稳定、不 flaky、实现简单；能第一时间发现“接口签名/字段名/响应结构”的变化
- 缺点：不能证明运行期返回体一定符合 schema，但能强约束“契约变化必须显式发生”

### Level 2（次优先）：关键端点响应体 JSONSchema 校验

只挑最核心的端点做“真实请求 → 校验响应体结构”：

```python
# 示例：校验 /api/auth/me 响应结构
def test_auth_me_response_schema(client, auth_headers):
    resp = client.get("/api/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "user" in body
    user = body["user"]
    assert "username" in user
    assert "role" in user
    assert "daily_quota" in user
    assert isinstance(user["daily_quota"], int)
```

优先覆盖的端点（约 15 个）：
- `/api/auth/register`、`/api/auth/login`、`/api/auth/me`
- `/api/generate`、`/api/generate_many`
- `/api/jobs/recent`、`/api/jobs/history`、`/api/jobs/{id}`
- `/api/community`
- `/api/providers`
- `/api/admin/users`、`/api/admin/config`

- 优点：覆盖关键链路、实现可控
- 缺点：需要少量测试数据准备，但成本远小于全量自动化

### Level 3（长期）：基于 OpenAPI 的生成式测试（Schemathesis 等）

自动生成请求与参数，校验响应；价值最大，但工程成本与维护成本也最高。
建议在 Phase 3/4 之后再考虑。

> **实施节奏**：Phase 1 先落地 Level 1；Phase 2/3 再补 Level 2；Level 3 视团队维护成本决定是否做。

---

## 7. 依赖与安装

| 包 | 用途 | 安装位置 |
|----|------|----------|
| `pytest` | Backend 测试框架 | backend/ |
| `pytest-asyncio` | 异步测试支持 | backend/ |
| `pytest-cov` | 覆盖率报告 | backend/ |
| `pytest-timeout` | 测试超时保护，防止 CI 卡死（v6 新增） | backend/ |
| `httpx` | HTTP 客户端（已在 requirements.txt） | backend/ |
| `playwright` | E2E 浏览器测试 | frontend/e2e/ |
| `@playwright/test` | Playwright 测试运行器 | frontend/e2e/ |

> **重要**：`pytest`、`pytest-asyncio`、`pytest-cov`、`pytest-timeout` 当前**未在 `backend/requirements.txt` 中声明**（仅全局安装），需补充到 `requirements-dev.txt`。

```bash
# Backend — 创建开发依赖文件
cat > backend/requirements-dev.txt << 'EOF'
pytest>=8.0
pytest-asyncio>=0.23
pytest-cov>=4.0
pytest-timeout>=2.2
EOF

pip install -r backend/requirements-dev.txt

# Frontend E2E（需要 node）
# 在 frontend/e2e/ 子目录中初始化，避免污染项目根目录
cd frontend/e2e
npm init -y
npm install -D @playwright/test
npx playwright install chromium --with-deps
```

#### Windows / PowerShell：创建 `requirements-dev.txt`（等价写法）

```powershell
$content = @'
pytest>=8.0
pytest-asyncio>=0.23
pytest-cov>=4.0
pytest-timeout>=2.2
'@

Set-Content -Path .\\backend\\requirements-dev.txt -Value $content -Encoding UTF8
pip install -r .\\backend\\requirements-dev.txt
```

---

## 8. 执行策略

### 本地开发（CI 前的快速反馈）

```bash
# API Integration Tests（无需启动服务器，< 30s）
pytest -c backend/pytest.ini backend/tests/test_api/ -v

# E2E Tests（Playwright 会按 playwright.config.ts 自动拉起后端 webServer，< 2 分钟）
cd frontend/e2e
npx playwright test --grep @smoke
```

#### Windows / PowerShell 本地执行

```powershell
# 运行 API tests
pytest -c .\backend\pytest.ini .\backend\tests\test_api\ -v

# 运行 E2E tests
cd .\frontend\e2e
npx playwright test --grep @smoke
```

#### 用“探活循环”替代固定 sleep（降低 CI / 本地 flaky）

固定 `sleep 3/5` 在 CI 和部分机器上会偶发不够。

- 若选择 **手动启动后端**（例如调试时不用 Playwright `webServer`），等待后端就绪请使用探活循环。
- 若使用 Playwright `webServer`，一般不需要单独写 wait step：Playwright 会在运行测试前等待 `webServer.url` 可访问。

- **Bash（CI 常用）**：
  ```bash
  for i in $(seq 1 30); do curl -sf http://localhost:8000/ && break || sleep 1; done
  ```
- **PowerShell（本地常用）**：
  ```powershell
  for ($i = 1; $i -le 30; $i++) {
    try { Invoke-WebRequest -Uri http://127.0.0.1:8000/ -UseBasicParsing -ErrorAction Stop; break }
    catch { Start-Sleep -Seconds 1 }
  }
  ```

### 触发时机

> 说明：下表是“目标态”。在 **最小可落地里程碑 / Phase 0-1** 阶段，建议 CI 先只启用 `api-tests`，等 Phase 3 有首批稳定的 `@smoke` 用例后再开启 `e2e-smoke`；`e2e-full` 建议最后再加（nightly）。

| 场景 | 自动触发？ |
|------|----------|
| git push 到 main | CI 运行：API tests + E2E smoke（最小集） |
| 任意 PR | CI 运行：API tests + E2E smoke（最小集） |
| nightly（定时） | CI 运行：E2E full suite（全量，允许更慢） |
| 本地开发 | 可选：pre-commit hook 运行 API tests only |
| UI 大改后 | 建议运行 E2E tests |

> **E2E smoke 约定**：需要被 PR 触发的最小 E2E 集请在用例标题中包含 `@smoke`（例如 `test("登录成功 @smoke", ...)`）。CI 使用 `--grep @smoke` 仅执行该子集；nightly 执行全量用例。

### 测试超时策略（v6 新增）

**问题**：如果 worker 卡住、SSE 连接未断开、或外部依赖无响应，测试可能无限等待，阻塞 CI。

**解决方案**：

1. **pytest 全局超时**：在 `backend/pytest.ini`（推荐）或 `backend/pyproject.toml` 中配置 `pytest-timeout`

```ini
# backend/pytest.ini
[pytest]
timeout = 30
# 超时方法：
# - Linux/macOS 可选 signal（更精确）
# - Windows 请不要使用 signal（不可用/不稳定），保持默认或使用 thread
# timeout_method = signal
```

2. **SSE 测试专用超时**：SSE 测试使用 `asyncio.wait_for`（Python 3.10+）或 `asyncio.timeout`（Python 3.11+）包裹流读取；或直接复用上文 `read_sse_event` helper（内部已带 timeout）

```python
@pytest.mark.asyncio
async def test_sse_connect_and_hello(app, auth_headers, read_sse_event):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
        async with ac.stream("GET", "/api/events", headers=auth_headers) as resp:
            event = await read_sse_event(resp.aiter_lines(), timeout_s=5.0)
            assert event.get("event") == "hello"
```

3. **Playwright 超时**：在 `playwright.config.ts` 中配置全局超时

```typescript
export default defineConfig({
  timeout: 30_000,        // 单个测试 30 秒
  expect: { timeout: 5_000 },  // 断言 5 秒
});
```

### 覆盖率报告集成（v6 新增）

**本地查看覆盖率**：

```bash
# 生成终端 + HTML 报告
pytest -c backend/pytest.ini backend/tests/test_api/ -v --cov=backend --cov-report=term-missing --cov-report=html

# HTML 报告位于 htmlcov/index.html
```

**CI 覆盖率集成**：

```yaml
# 在 CI workflow 的 api-tests job 中添加：
- name: API Integration Tests with Coverage
  run: pytest -c backend/pytest.ini backend/tests/test_api/ -v --tb=short --cov=backend --cov-report=term-missing --cov-report=xml

- name: Upload Coverage Report
  if: always()
  uses: actions/upload-artifact@v4
  with:
    name: coverage-report
    path: coverage.xml
```

> **可选**：集成 Codecov 或 Coveralls 自动化覆盖率追踪。Phase 1 暂不引入，等测试稳定后再添加。

### CI 配置（`.github/workflows/test.yml`）

```yaml
name: Test
on:
  pull_request:
  push:
    branches: [main]
  schedule:
    - cron: "0 3 * * *"  # nightly
jobs:
  api-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install deps
        run: pip install -r backend/requirements.txt -r backend/requirements-dev.txt
      - name: API Integration Tests
        run: pytest -c backend/pytest.ini backend/tests/test_api/ -v --tb=short --cov=backend --cov-report=term-missing --cov-report=xml

      - name: Upload Coverage Report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: coverage-report
          path: coverage.xml

  e2e-smoke:
    needs: api-tests
    # 建议用开关门控：Phase 0-1 先只启用 api-tests，等 Phase 3 有稳定 @smoke 用例后再打开 e2e。
    # 在仓库 Settings → Variables 中设置 ENABLE_E2E=1 即可启用。
    if: vars.ENABLE_E2E == '1' && github.event_name != 'schedule'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
      - name: Install backend deps
        run: pip install -r backend/requirements.txt -r backend/requirements-dev.txt
      - name: Install Playwright
        run: cd frontend/e2e && npm install && npx playwright install chromium --with-deps
      - name: E2E Smoke Tests
        run: cd frontend/e2e && npx playwright test --grep @smoke --retries=1 --trace=on-first-retry

  e2e-full:
    needs: api-tests
    if: vars.ENABLE_E2E == '1' && github.event_name == 'schedule'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
      - name: Install backend deps
        run: pip install -r backend/requirements.txt -r backend/requirements-dev.txt
      - name: Install Playwright
        run: cd frontend/e2e && npm install && npx playwright install chromium --with-deps
      - name: E2E Full Suite
        run: cd frontend/e2e && npx playwright test --retries=1 --trace=on-first-retry
```

---

## 9. 分阶段实施路线图（修订）

### 最小可落地里程碑（2~3 天）

为避免“路线图很完整但迟迟无法开始”，在 Phase 0/1 前插入一个最小里程碑：

- [x] Phase 0 的 env-var 隔离跑通：`pytest` 能在不依赖本地 `data/` 的前提下 import 并创建 app/state
- [x] 落地 1 个 `test_auth.py`（包含：注册成功、密码错误 401、无 token 401）
- [x] 落地 1 个 `test_jobs.py`（包含：generate 创建 job、quota 扣减边界）
- [x] CI 先只跑 API tests（E2E 暂缓），保证 PR 不再“静默破坏”

**验收标准**：
- `pytest -c backend/pytest.ini backend/tests/test_api/ -v` 在本地通过，0 fail
- CI pipeline 绿色
- 覆盖至少 3 个核心端点（register、login、generate）
- `AI_MUSIC_TEST_MODE=1` 时，调用 `/api/generate` 后 job 最终进入 `succeeded`
- `rec.output_path` 指向的文件存在且非空，且可通过 `/api/audio/{job_id}` 正常下载（返回 200）
- **`clear_for_tests()` 已在 `JobStore` 和 `UserStore` 中实现，`db_clean` fixture 使用该方法**（v6 新增）

---

### Phase 0 — 测试基础设施适配（第 0-1 周）

**目标**: 解决 STATE 全局单例和 Worker 真实调用两大障碍，使 API 测试可行

- [x] **（首个 PR，阻塞后续所有测试）在 `JobStore` / `UserStore` 中实现 `clear_for_tests()` 方法**：内部加锁 + DELETE + commit，避免测试直接依赖 `_lock` / `_connect()` 等内部实现细节。**v6 强制要求**：不再允许临时使用 `_connect()` + DELETE 方案（伪代码见第 4 节 `clear_for_tests()` 段落）
- [x] **（阻塞 Provider Stub）确认 `_run_job()` 内部调用链的实际函数签名**：`rg -n "def _publish_job_status" backend/workers.py` 确认参数列表；`rg -n "def set_status" backend/storage.py` 确认 `JobStore.set_status()` 是否接受 `output_path` 关键字参数。若签名不匹配，需调整 3.2 节伪代码后再实施 Stub
- [x] 在 `backend/tests/test_api/` 中创建 `test_env.py`（module-level 环境变量设置）和 `conftest.py`，在 session 级别设置测试环境变量（明确覆盖关键 env，避免依赖本机 `config/providers.local.json`）
- [x] **实现 `db_clean` fixture**：使用 `clear_for_tests()` 清理两套 DB 的关键表（v6 不再允许临时方案）
- [x] 实现 `AI_MUSIC_TEST_MODE=1` Provider Stub：在 `_run_job()` 开头插入条件分支，worker 在测试模式下跳过外部 API 调用，直接写占位音频文件并将 job 标记为 succeeded（参见 3.2 节伪代码）
- [x] **WAV 实现决策**：不新增 MP3 fixture；`AI_MUSIC_TEST_MODE=1` 在内存中生成固定短 WAV，供 audio 测试通过 RIFF/WAVE magic-bytes 校验复用
- [x] 验证：`pytest -c backend/pytest.ini backend/tests/test_api/` 在环境变量驱动下能正常 import main
- [x] 验证：`ACESTEP_BASE_URL=http://localhost:0` 使 worker 连接失败不崩溃
- [x] 验证：`AI_MUSIC_TEST_MODE=1` 使 generate 成功链路可测试（job → succeeded，文件存在且可下载）
- [x] 创建 `backend/requirements-dev.txt`，声明 `pytest>=8.0`、`pytest-asyncio>=0.23`、`pytest-cov>=4.0`、`pytest-timeout>=2.2`

**交付物**: API 测试框架可运行，为 Phase 1 铺路

> Phase 0 是所有后续测试的前提。不解决此问题，Phase 1 的所有测试都无法工作。

---

### Phase 1a — Backend API 集成测试：核心链路（第 2 周）

**目标**: 覆盖认证和生成这两个核心链路，确保基本功能不回退

- [x] `test_auth.py` — 注册/登录/me/me(update)/密码修改，完整错误矩阵
- [x] `test_jobs.py` — generate / generate_many / generate_store / cancel / delete
- [x] `test_quota.py` — quota 消耗/退还/耗尽边界
- [x] `test_contract.py` — OpenAPI Schema 快照（Level 1）
- [x] `test_sse.py` — SSE 基础连接与认证（未认证被拒绝、认证后能连接）

**交付物**: 核心 API 测试通过率 100%，覆盖 auth + jobs + quota + SSE 基础

---

### Phase 1b — Backend API 集成测试：扩展端点（第 3 周）

**目标**: 覆盖剩余日常功能端点，补齐音频、上传、历史、社区、Provider 链路

- [x] `test_audio.py` — audio/{id} / audio/{id}.mp3 / community audio — 权限与路径安全（B2、B6）。**必须包含 WAV magic bytes 验证**：下载音频后检查 `b'RIFF'` + `b'WAVE'`，确保 test_mode 产出的是有效 WAV 而非空文件
- [x] `test_upload.py` — uploads/audio — 文件类型校验与大小限制（B13）
- [x] `test_providers.py` — providers list / random_sample
- [x] `test_history.py` — jobs/recent / jobs/history / jobs/{id} / jobs (list)
- [x] `test_community.py` — publish / unpublish / community / community audio

**交付物**: 日常功能端点测试通过率 100%

---

### Phase 1c — Backend API 集成测试：安全与高级场景（第 4 周）

**目标**: 覆盖 admin 权限矩阵、worker 状态流、并发一致性、边界值和安全场景

- [x] `test_admin.py` — admin 端点权限矩阵（见上方 Admin 测试矩阵），含 B14 schema 校验
- [x] `test_workers.py` — worker 单元测试：`run_with_retry` 重试逻辑、失败配额退还、`queued→running→succeeded` / `queued→running→failed` 状态流
  > 注意：`test_workers.py` 放在 `backend/tests/` 而非 `test_api/`，因为它是纯单元测试，不依赖 API 层和 TestClient
- [x] 并发测试 — 并发 generate 请求的 quota 一致性（B8）。**实现方案**：使用 `asyncio.gather` + 多个 `httpx.AsyncClient` 并发发送 N 个 generate 请求，完成后断言各用户的 quota 扣减正确。由于 Phase 1 不可使用 `pytest-xdist`，并发必须在单个测试函数内通过 async 协调。

  > **独立用户原则**：并发测试中每个请求必须使用独立的用户（独立 auth_headers），避免后端对同一用户的速率限制或锁机制干扰测试结果。通过 `multi_auth_headers` fixture 批量创建。

  ```python
  # conftest.py 中新增 fixture（示例：fixture 自带 params，避免与 @parametrize 重复）
  import os
  import uuid

  import pytest

  @pytest.fixture(params=[5])
  def multi_auth_headers(client, test_id, request) -> list[dict[str, str]]:
      """批量创建 N 个独立用户的 auth_headers 列表（供并发测试使用）。"""
      count = int(request.param)
      headers_list: list[dict[str, str]] = []

      admin_username = os.environ.get("AI_MUSIC_ADMIN_USERNAME", "admin")
      admin_password = os.environ.get("AI_MUSIC_ADMIN_PASSWORD", "adminpw")

      # 复用同一个 admin session 创建 invite codes
      resp = client.post("/api/auth/login", json={"username": admin_username, "password": admin_password})
      assert resp.status_code == 200, f"Admin login failed: {resp.text}"
      admin_token = resp.json()["token"]
      admin_h = {"Authorization": f"Bearer {admin_token}"}

      for _ in range(count):
          invite = client.post("/api/admin/invite-codes", headers=admin_h).json()["invite_code"]["code"]
          username = f"ctest_{test_id}_{uuid.uuid4().hex[:6]}"
          reg = client.post(
              "/api/auth/register",
              json={"username": username, "password": "testpass123", "invite_code": invite},
          )
          assert reg.status_code == 200, f"Register failed: {reg.text}"
          headers_list.append({"Authorization": f"Bearer {reg.json()['token']}"})

      return headers_list

  # 测试代码（示例）
  import asyncio
  import httpx

  @pytest.mark.asyncio
  async def test_concurrent_generate_quota_consistency(app, multi_auth_headers):
      """并发 generate 请求后，每个用户的 quota 扣减 = 1。"""
      transport = httpx.ASGITransport(app=app)
      async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
          # 获取各用户初始 quota
          quota_before: list[dict] = []
          for headers in multi_auth_headers:
              me = (await ac.get("/api/auth/me", headers=headers)).json()
              quota_before.append(me["user"]["quota"])

          async def do_generate(idx: int, headers: dict[str, str]) -> int:
              resp = await ac.post(
                  "/api/generate",
                  json={"prompt": f"concurrent test {idx}", "duration_sec": 10},
                  headers=headers,
              )
              return resp.status_code

          # 每个用户并发发 1 个 generate 请求
          results = await asyncio.gather(
              *[do_generate(i, headers) for i, headers in enumerate(multi_auth_headers)]
          )

          # 验证每个用户的 quota 扣减
          for i, headers in enumerate(multi_auth_headers):
              me = (await ac.get("/api/auth/me", headers=headers)).json()
              quota_after = me["user"]["quota"]
              if results[i] == 200:
                  assert int(quota_after["used"]) - int(quota_before[i]["used"]) == 1
  ```
- [x] 边界值测试 — 用户名/密码长度、prompt 最大长度、invite code 格式、quota 0/1/最大值
- [x] 安全测试 — output_path 路径穿越（B2）、_serialize_job JSON 解析失败（B5）、share_permission 未强制执行（B6）

**交付物**: `pytest -c backend/pytest.ini backend/tests/test_api/` 通过率 100%，所有 API 端点有测试覆盖

> **并行执行警告**：Phase 1 的 API tests **不可使用 `pytest-xdist` 并行执行**，因为所有 test 共享同一个 STATE 实例和 DB 连接。并行会导致数据竞争和不可预测的测试结果。如需并行，必须先改造为每个 worker 独立 data_dir（当前不在 scope 内）。

---

### Phase 2 — Playwright E2E 基础设施（第 5-6 周）

**目标**: 让 Playwright 在项目中跑起来，选择关键场景覆盖。**Phase 2 暂不引入 Page Object**，直接在 spec 中写选择器交互；等 E2E 测试超过 ~15 个 spec 或选择器重复度高时再提取到 `pages/app.page.ts`。

- [x] `npm init -y && npm install -D @playwright/test`（在 `frontend/e2e/` 子目录）
- [x] 配置 `playwright.config.ts`（双 viewport projects）
- [x] `conftest.ts` — test user factory（通过 API 创建 + 清理）
- [x] `auth/register.spec.ts` — 完整注册流程
- [x] `auth/login.spec.ts` — 登录 + Enter 提交
- [x] `create/generate.spec.ts` — 正常生成流程（真实后端 + `page.route()` mock 错误）

**交付物**: `npx playwright test` 在 Chromium 上通过率 100%

---

### Phase 3 — 关键 E2E 场景（第 7-8 周）

**目标**: 覆盖 prd.md 审查发现中的 UI 问题，确保不再重现

> ⚠️ **F3 依赖前置**：以下标注 `🗳 依赖 F3` 的测试项依赖 prd.md 中 F3（Toast 系统无效）的修复。在 F3 修复前，这些测试应使用 `page.on('console')` 验证错误日志输出，或通过 `page.route()` 拦截后检查 DOM 中的错误容器（非 Toast），待 F3 修复后再改为视觉 Toast 断言。建议将 F3 修复安排在 Phase 3 开始之前或 Phase 3 早期。

- [x] `mobile/mobile_layout.spec.ts` — 移动端独立 DOM 结构，切换后正确显示
- [x] `mobile/mobile_generate.spec.ts` — 移动端生成流程
- [x] `create/generate_quota_exhausted.spec.ts` — 配额用尽的 UI 提示正确 🗳 依赖 F3
- [x] `create/generate_error.spec.ts` — `page.route()` mock 错误响应，Toast 正确显示 🗳 依赖 F3
- [x] `sticky_player_overlap.spec.ts` — sticky player 不遮挡表单按钮
- [x] `redirect_401.spec.ts` — JWT 过期后正确处理
- [x] `clear_prompt.spec.ts` — 清除按钮重置输入框
- [x] `enter_submit.spec.ts` — Enter 键触发生成
- [x] `poll_timer_vs_sse.spec.ts` — 生成后验证无重复 API 调用（F11）
- [x] `viewport_resize.spec.ts` — viewport 切换后历史列表正常渲染（F4）
- [x] `pages/app.page.ts` — **可选**：提取重复选择器为 Page Object（若 spec 文件超过 ~15 个或选择器重复度高时引入）
- [x] OpenAPI 契约 Level 2 — 关键端点响应体 JSONSchema 校验

---

### Phase 4 — CI 集成 + SSE 完整测试（第 9-10 周）

**目标**: 自动化运行，融入开发流程

- [x] 添加 `.github/workflows/test.yml`
- [x] `test_sse.py` 补充完整 SSE 测试 — 事件接收、多连接；浏览器自动重连由 `sse/sse_reconnect.spec.ts` 覆盖
- [x] `sse/sse_reconnect.spec.ts` — E2E SSE 断线重连 + pollTimer 无重复调用（F11）
- [x] `mobile_viewport.spec.ts` — 移动端视口切换后布局正确（综合测试）
- [x] pre-commit hook（可选，仅 API tests）：不引入本地 hook，CI 已覆盖 API tests；可选项按“CI 替代”关闭
- [x] OpenAPI 契约 Level 3 评估 — 暂不引入 Schemathesis；当前以快照 + Level 2 关键响应体验证作为维护成本可控的契约边界

---

## 10. 测试覆盖率目标

| 阶段 | 目标 | 度量方式 |
|------|------|----------|
| Phase 1a 完成后 | API 路由层覆盖率 ≥ 60% | `pytest --cov=backend --cov-report=term-missing` |
| Phase 1b 完成后 | API 路由层覆盖率 ≥ 80% | 同上 |
| Phase 1c 完成后 | API 路由层覆盖率 ≥ 90% | 同上 |
| Phase 3 完成后 | E2E 核心用户链路 100%（注册→生成→播放→历史） | 人工确认 |
| 长期目标 | Backend 单元 + API 集成总覆盖率 ≥ 85% | CI 自动报告 |

> **覆盖率是辅助指标，不是目标**。100% 覆盖率不等于没有 bug。优先覆盖关键链路和高风险区域（auth、quota、文件服务）。

### 测试命名与标记规范

| 标记 | 用途 | 示例 |
|------|------|------|
| `@smoke` | E2E 最小集，PR 必跑 | `test("登录成功 @smoke", ...)` |
| `@slow` | 耗时测试（并发、边界值），nightly 跑 | `test("并发 quota 一致性 @slow", ...)` |
| `@security` | 安全相关测试（路径穿越、权限绕过） | `test("output_path 路径穿越 @security", ...)` |

- pytest 中使用 `@pytest.mark.slow` / `@pytest.mark.security` 标记
- Playwright 中使用 `test("... @smoke", ...)` 标题约定，CI 通过 `--grep @smoke` 过滤

### pytest 配置（v6 新增）

在 `backend/pytest.ini`（推荐，跨平台最直观）或 `backend/pyproject.toml` 中统一配置。

> **配置发现规则提醒**：本文档多数命令是从仓库根目录运行 `pytest backend/tests/test_api/ ...`。为避免 pytest 未加载到 `backend/pytest.ini`，建议统一使用以下任一方式：
> - 从根目录运行时显式指定配置：`pytest -c backend/pytest.ini backend/tests/test_api/ -v`
> - 或先 `cd backend` 再运行 `pytest tests/test_api/ -v`

```ini
# backend/pytest.ini（推荐）
[pytest]
testpaths = tests
timeout = 30
markers =
    slow: marks tests as slow (deselect with '-m "not slow"')
    security: marks tests as security-related
asyncio_mode = auto
```

> 若后续希望把配置迁移到 `backend/pyproject.toml`，可使用 `[tool.pytest.ini_options]` TOML 格式的等价配置。

### 测试数据工厂

`auth_headers` fixture 已提供认证用户，但更复杂的测试场景（已有 job、已发布音频、不同权限用户）需要更丰富的数据准备。

**建议**：在 `backend/tests/test_api/conftest.py` 中增加工厂函数：

```python
@pytest.fixture
def factories(client, auth_headers):
    """测试数据工厂，提供快速创建测试数据的方法。"""
    class Factories:
        def __init__(self, client, headers):
            self._client = client
            self._headers = headers

        def create_job(self, prompt="test song", duration_sec: int = 30, **kwargs):
            """创建一个 job 并返回 job_id（不等待完成）。"""
            resp = self._client.post(
                "/api/generate",
                json={"prompt": prompt, "duration_sec": int(duration_sec), **kwargs},
                headers=self._headers,
            )
            assert resp.status_code == 200, resp.text
            return resp.json()["job_id"]

        def wait_job(self, job_id: str, *, expect_status: str = "succeeded", timeout_s: float = 5.0):
            """轮询 job 状态直到到达 expect_status（避免 race 导致 publish 409）。"""
            import time

            deadline = time.time() + float(timeout_s)
            last = None
            while time.time() < deadline:
                r = self._client.get(f"/api/jobs/{job_id}", headers=self._headers)
                assert r.status_code == 200, r.text
                last = r.json()
                if last.get("status") == expect_status:
                    return last
                time.sleep(0.1)
            raise AssertionError(f"job did not reach {expect_status}: {last}")

        def create_succeeded_job(self, prompt="succeeded song", **kwargs):
            """创建并等待 job 进入 succeeded。"""
            job_id = self.create_job(prompt, **kwargs)
            self.wait_job(job_id, expect_status="succeeded")
            return job_id

        def create_published_job(self, prompt="published song", share_permission: str = "listen_only"):
            """创建并发布一个 job（用于社区测试）。"""
            job_id = self.create_succeeded_job(prompt)
            resp = self._client.post(
                f"/api/jobs/{job_id}/publish",
                json={"share_permission": share_permission},
                headers=self._headers,
            )
            assert resp.status_code == 200, resp.text
            return job_id

    return Factories(client, auth_headers)
```

> 工厂函数按需扩展，不需要一次性覆盖所有场景。Phase 1a 先提供 `create_job`，后续逐步补充。

---

## 11. 关键文件变更汇总

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/storage.py` | **修改** | `JobStore` 新增 `clear_for_tests()` 方法（内部加锁 + DELETE + commit） |
| `backend/user_store.py` | **修改** | `UserStore` 新增 `clear_for_tests(exclude_admin=False)` 方法 |
| `backend/requirements-dev.txt` | **新增** | 开发依赖：pytest, pytest-asyncio, pytest-cov |
| `backend/tests/test_api/` | 新增 | API 集成测试目录 |
| `backend/tests/test_api/test_env.py` | **新增** | module-level 环境变量设置（v6：提取自 conftest.py，确保导入时序安全） |
| `backend/tests/test_api/conftest.py` | 新增 | session-level env setup, app fixture, auth helper, ensure_admin, db_clean（使用 clear_for_tests()） |
| `backend/tests/test_api/test_auth.py` | 新增 | 认证相关测试 |
| `backend/tests/test_api/test_jobs.py` | 新增 | 生成任务测试（含 generate、generate_many、generate_store、cancel、delete、inpaint、stems、batch_delete） |
| `backend/tests/test_api/test_history.py` | 新增 | 历史查询测试 |
| `backend/tests/test_api/test_community.py` | 新增 | 社区/发布测试 |
| `backend/tests/test_api/test_audio.py` | **新增** | 音频服务测试 — 权限与路径安全 |
| `backend/tests/test_api/test_upload.py` | **新增** | 文件上传测试 — 类型校验与大小限制 |
| `backend/tests/test_api/test_providers.py` | **新增** | Provider 列表与随机采样测试 |
| `backend/tests/test_api/test_quota.py` | 新增 | 配额测试 |
| `backend/tests/test_api/test_admin.py` | 新增 | 管理端点权限测试（含 Admin 测试矩阵） |
| `backend/tests/test_api/test_sse.py` | 新增 | SSE 基础连接、认证、事件接收与多连接 fanout 测试 |
| `backend/tests/test_api/test_contract.py` | 新增 | OpenAPI Schema 快照 + Level 2 关键端点响应体契约校验 |
| `backend/tests/test_api/test_concurrency.py` | 新增 | 单测试函数内并发 generate 请求，验证独立用户 quota 一致性 |
| `backend/tests/test_api/test_validation.py` | 新增 | 边界值与安全回归测试（auth boundary、prompt 最大长度、JSON 恢复） |
| `backend/tests/test_api/snapshots/` | 新增 | OpenAPI schema 快照目录 |
| `backend/tests/test_workers.py` | **新增** | Worker 单元测试：job 状态流、重试、配额退还（放在 tests/ 而非 test_api/，纯单元测试） |
| `backend/tests/conftest.py` | 扩展 | 保持现有 DB fixture 不变，test_api/conftest 独立扩展 |
| `frontend/e2e/` | 新增 | Playwright E2E tests |
| `frontend/e2e/playwright.config.ts` | 新增 | 双 viewport projects + 失败策略（截图/视频/trace）+ webServer 配置 |
| `frontend/e2e/conftest.ts` | 新增 | Test user factory |
| `frontend/e2e/pages/app.page.ts` | 新增 | Page Object（Phase 3 可选引入） |
| `frontend/e2e/sse/sse_reconnect.spec.ts` | **新增** | SSE 断线重连 + pollTimer 无重复调用 |
| `frontend/e2e/mobile_viewport.spec.ts` | **新增** | 移动端 viewport 切换后布局正确性综合测试 |
| `.github/workflows/test.yml` | 新增 | CI 配置（API tests + E2E smoke；nightly E2E full；E2E 通过 Playwright `webServer` 启动后端并启用 test mode） |
| `.github/workflows/ci.yml` | 修改 | Legacy CI 同步安装 `requirements-dev.txt`，避免缺失 `pytest-timeout` / `pytest-cov` |
| `package.json` | 新增 | Node 依赖（Playwright），位于 `frontend/e2e/` 子目录，避免污染项目根目录 |
| `backend/pytest.ini`（或 `backend/pyproject.toml`） | **新增** | pytest 配置：timeout=30, markers, asyncio_mode（v6 新增） |
| `backend/workers.py` | 修改 | 添加 `AI_MUSIC_TEST_MODE=1` Provider Stub 分支（必须落在 `_run_job()` 内部，在调用 ACEStepClient 之前拦截，保留 rate limiter 和 queued→running 状态转换） |

---

## 12. 风险与缓解（修订）

| 风险 | 影响 | 缓解 |
|------|------|------|
| STATE 全局单例导致测试无法隔离 | API 测试完全不可行 | Phase 0 通过 env-var 解决，是所有后续测试的前提 |
| Worker 真实调用外部 API | 测试环境产生副作用 | `ACESTEP_BASE_URL=http://localhost:0` 使连接立即失败 + `AI_MUSIC_TEST_MODE=1` Provider Stub 覆盖成功链路 |
| 测试误用本机 `config/providers.local.json`（真实密钥/端点） | 测试可能误打外部 API 或污染本机数据 | API tests 在 `conftest.py` 覆盖关键 env；E2E 通过 Playwright `webServer.env` 覆盖（含 `ACESTEP_BASE_URL` + `AI_MUSIC_TEST_MODE`） |
| E2E 测试不稳定（flaky）| 误报 CI 失败 | Playwright 增强等待条件；失败自动重试 1 次；截图 + 视频 + trace 保留 |
| SSE 长连接干扰测试 | 测试间相互阻塞 | 每个测试用独立 page；SSE 在 afterEach 中确保断开 |
| 移动端双 DOM 树加倍测试量 | 测试维护成本高 | 双 viewport projects 共享同一套 spec，只切换选择器 |
| E2E mock 错误依赖真实后端 | 需要后端 server 可用（即使部分请求被 `page.route()` 拦截） | 统一由 Playwright `webServer` 启动后端并等待 `webServer.url` 就绪；CI 不再手动 start server，避免端口冲突与重复等待逻辑 |
| API 测试对 env-var 注入时机敏感 | session fixture 顺序问题 | conftest.py 两层防护：module-level setdefault + session fixture |
| Playwright 无 Node.js 构建系统 | 项目根目录无 package.json | `npm init -y` 初始化，手动管理依赖 |
| 测试数据互相污染 | 交叉测试失败 | Session 级 data_dir + Function 级表清理（双 DB），db_clean fixture 可运行实现 |
| Job 未等待终态导致跨测试干扰 | 后台 worker/队列在下一条测试中继续写 DB 或推送 SSE，导致偶现 flaky | 约束：任何创建 job 的测试必须等待 job 进入 `succeeded/failed`；统一使用 `wait_job()` 工厂方法 |
| 测试并行执行导致数据竞争 | 不可预测的测试失败 | 明确标注 Phase 1 不可使用 pytest-xdist 并行；需独立 data_dir 改造后才可并行 |
| db_clean fixture 依赖 Store 内部 API | 若直接依赖内部字段（如 `_conn`）或缺少封装，易在重构时破坏测试 | v6 强制：Phase 0 首个 PR 实现 `clear_for_tests()`，不再允许临时方案 |
| SSE 测试中 `TestClient.stream()` 兼容性 | `iter_lines()` 可能无法正确解析 SSE 事件格式（`\n\n` 分隔） | v6 默认采用方案 B（AsyncClient + ASGITransport）；方案 A 降级为备选 |
| 测试无超时保护导致 CI 卡死 | worker 卡住或 SSE 连接未断开时，测试无限等待 | v6 新增 pytest 全局超时（30s）+ SSE 专用 `asyncio.wait_for`/`read_sse_event(timeout_s=...)` + Playwright timeout 配置 |
| 临时目录未清理导致磁盘占用 | CI 和本地多次运行后临时目录累积 | `setup_test_env` 使用 `TemporaryDirectory(... )`，session 结束自动清理 `AI_MUSIC_DATA_DIR`；CI 额外依赖 runner 自动清理 |
| 并发测试共享 auth_headers 导致不稳定 | 后端对同一用户有速率限制或锁机制，并发请求行为不可预测 | v7 已解决：新增 `multi_auth_headers` fixture，每个并发请求使用独立用户 |
| `auth_headers` 依赖 admin 但 admin 可能不存在 | `db_clean` 清空 users 表后，若 admin 创建依赖启动时序，fixture 可能失败 | v6 新增 `ensure_admin` fixture，每条测试前验证 admin 可登录并发出警告 |

---

## 13. 修订历史

> 完整修订对比（v1 → v7）已分离至 [`testing-plan-changelog.md`](testing-plan-changelog.md)，主文档仅保留当前版本（v7）的变更摘要。

**v7 修订要点**（评审后优化，2026-05-14）：

| 变更 | 说明 |
|------|------|
| `clear_for_tests()` 伪代码 | 第 4 节新增完整实现参考，与 `_run_job` Stub 同等详细度 |
| `set_status` 签名验证 | Phase 0 新增 checklist：实施前确认函数签名，避免伪代码与实际不匹配 |
| Toast E2E 依赖 F3 | Phase 3 标注 F3 依赖，说明修复前的临时断言策略 |
| SSE 事件解析 helper | 新增 `read_sse_event` helper（fixture + 读取器函数），统一封装 SSE 事件读取逻辑 |
| `TEST_ENV` 常量统一 | `test_env.py` 导出常量字典，`conftest.py` 复用，避免 env 列表漂移 |
| 并发测试独立用户 | 新增 `multi_auth_headers` fixture，避免共享用户导致的不稳定 |
| 修订历史分离 | 完整历史移至 `testing-plan-changelog.md`，减少主文档篇幅 |

---

## 14. 文档维护建议（可选，但强烈推荐）

为避免后续实施阶段“文档很长但改一处牵一片”，建议对本文档做以下维护约定（不影响本计划的技术正确性）：

1. **把“可复制执行的模板”集中存放**：将 `test_env.py`、`conftest.py`、`playwright.config.ts`、`.github/workflows/test.yml` 等大段模板集中在各章节末尾的“模板区”，正文只保留约束/验收标准/决策点。
2. **所有示例代码必须满足“最小可运行”**：例如 `httpx.AsyncClient` 示例必须显式使用 `ASGITransport(app=app)`，避免读者按文档照抄却触发真实网络请求。
3. **跨平台命令一律给出 PowerShell 等价写法**：例如 snapshot 更新除了 `cp` 外同步给出 `Copy-Item`，避免 Windows 同学在落地时额外查资料。
4. **Playwright 配置的 Node 模块制式说明**：本文档示例使用 `__dirname`（CommonJS 语义）。若项目启用 ESM（`"type":"module"` 或 TS 输出 ESM），需要改用 `import.meta.url` + `fileURLToPath` 获取目录路径再 `path.resolve(...)`。
5. **避免重复叙述**：CI 启动策略、E2E test mode 前提、数据隔离策略这三处内容在文档中出现多次时，保留“唯一权威段落”，其他位置用链接/引用指向，减少漂移风险。
6. **（v6 新增）唯一权威段落映射**：
  - `AI_MUSIC_TEST_MODE` → 3.2 节（权威说明），其他位置引用“参见 3.2 节”
  - 数据隔离策略 → 4 节 conftest 架构（权威说明），其他位置引用“参见 4 节 conftest 架构”
   - SSE 测试策略 → 3.4 节（权威说明）+ 4 节 SSE 测试策略（实现细节）
7. **（v7 修订）`test_env.py` 维护规则**：新增环境变量时只需更新 `test_env.py` 中的 `TEST_ENV` 字典，`conftest.py` 通过 `from test_env import TEST_ENV` 自动同步，无需维护两份列表。注意 `AI_MUSIC_DATA_DIR` 不在 `TEST_ENV` 中（它由 session fixture 动态设置为临时目录）。
8. **修订历史维护**：完整修订历史记录在 [`testing-plan-changelog.md`](testing-plan-changelog.md)，主文档第 13 节仅保留当前版本的变更摘要。后续修订时同步更新两个文件。
9. **代码块可复制执行性**：所有示例代码块（Python/TS/YAML/INI）必须使用 ASCII 引号（`'` / `"` / `"""`），禁止混入 `“”` 等弯引号。建议在提交前执行 `rg -n '“|”' testing-plan.md` 自检，避免读者照抄后语法错误。
