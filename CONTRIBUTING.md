# Contributing to you2music

Thank you for your interest in contributing!

## Development Setup

### Prerequisites

- Python 3.10+
- [ACE-Step](https://acemusic.ai/) API key
- Node.js 20+ for Playwright E2E tests

### 1. Clone & Install

```bash
git clone <your-fork-url>
cd you2music
pip install -r backend/requirements.txt
pip install -r backend/requirements-dev.txt
```

### 2. Configure

```bash
cp config/providers.local.example.json config/providers.local.json
# Edit providers.local.json and fill in your API keys
```

### 3. Run Tests

```powershell
# One-command full validation: backend tests + ruff + full E2E
.\tools\test_all.ps1

# PR-sized validation: backend tests + ruff + E2E smoke
.\tools\test_all.ps1 -Smoke

# Skip dependency/browser installation when already prepared
.\tools\test_all.ps1 -Smoke -SkipInstall -SkipBrowserInstall
```

The script supports `-SkipBackend`, `-SkipE2E`, `-Ui`, `-E2EPort 8010`, and `-E2EWorkers 2`. By default it selects an available E2E port, disables reuse of existing local servers, and runs E2E with one worker to avoid multiple browser projects competing for the same test-mode provider queue. It uses `.tmp\npm-cache` when `npm_config_cache` is not set, avoiding permission issues with global npm cache directories on Windows.

```powershell
# Backend: unit + API integration tests
python -X utf8 -m pytest -c backend\pytest.ini backend\tests -q

# Backend: API integration tests only
python -X utf8 -m pytest -c backend\pytest.ini backend\tests\test_api -q

# Lint
ruff check .
```

API integration tests are isolated from local runtime data. They set test-only environment variables in `backend/tests/test_api/test_env.py`, use a temporary data directory, and run provider success paths through `AI_MUSIC_TEST_MODE=1`. Test-mode audio is WAV; assertions check `RIFF/WAVE` bytes instead of MP3 fixtures.

#### Frontend E2E

```powershell
cd frontend\e2e
npm install
npx playwright install chromium webkit

# PR-sized smoke subset
npm run test:smoke

# Full E2E suite
npm test

# Interactive debugging
npm run test:ui
```

Playwright starts the backend automatically through `frontend/e2e/playwright.config.ts`. It uses an isolated temporary `AI_MUSIC_DATA_DIR`, fake provider credentials, and `AI_MUSIC_TEST_MODE=1`. Direct `npm test` runs use port `8000` unless `YOU2MUSIC_E2E_PORT` is set, and default to `YOU2MUSIC_E2E_WORKERS=1`; existing servers are reused only when `YOU2MUSIC_E2E_REUSE_SERVER=1` is set explicitly.

### 4. Start the Server

```bash
# FastAPI mode (recommended)
$env:AI_MUSIC_JWT_SECRET = "your-secret-here"
python backend/main.py

# stdlib mode (zero-dependency)
python backend/stdlib_server.py
```

## Project Structure

```
backend/
  main.py          # FastAPI entry point
  stdlib_server.py # Zero-dependency HTTP server
  config.py        # Configuration loading
  storage.py       # SQLite job store + API log store
  user_store.py    # SQLite user store
  concurrency.py   # Provider queues, rate limiters, retry logic
  workers.py       # Job execution with API logging
  key_pool.py      # Multi-key management with health tracking
  providers/       # ACE-Step API clients
  static/          # Frontend HTML
  tests/           # Unit tests
```

## Code Style

- Python: follow existing patterns (type hints, docstrings)
- HTML/JS: inline styles, vanilla JS (no framework)
- Run `ruff check .` before committing

## Pull Request Process

1. Fork the repo and create a branch from `master`
2. Make your changes and add tests if applicable
3. Ensure `.\tools\test_all.ps1 -Smoke` passes
4. For backend-only changes, `python -X utf8 -m pytest -c backend\pytest.ini backend\tests -q` and `ruff check .` are acceptable
5. Open a PR with a clear description of what changed and why

## Reporting Issues

- Check existing issues before opening a new one
- Include Python version, OS, and relevant config (no secrets!)
- Steps to reproduce are very helpful
