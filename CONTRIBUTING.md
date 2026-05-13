# Contributing to you2music

Thank you for your interest in contributing!

## Development Setup

### Prerequisites

- Python 3.10+
- [ACE-Step](https://acemusic.ai/) API key

### 1. Clone & Install

```bash
git clone <your-fork-url>
cd you2music
pip install -r backend/requirements.txt
```

### 2. Configure

```bash
cp config/providers.local.example.json config/providers.local.json
# Edit providers.local.json and fill in your API keys
```

### 3. Run Tests

```bash
cd backend
python -m pytest tests/ -v
```

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
3. Ensure `python -m pytest backend/tests/ -v` passes
4. Open a PR with a clear description of what changed and why

## Reporting Issues

- Check existing issues before opening a new one
- Include Python version, OS, and relevant config (no secrets!)
- Steps to reproduce are very helpful
