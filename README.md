# AI Music Tool (API + Singing)

Small-scope internal tool that generates songs (optionally with vocals) via the **ElevenLabs Music API**, with a minimal web UI and local storage.

## What this is (and isn't)

- ✅ Goal: "Prompt → generate → listen → download" end-to-end flow for small-group use.
- ✅ Supports multi-candidate generation (2–4 variations per prompt).
- ✅ Supports “Extend” (implemented as re-compose with longer duration; best-effort, not a true continuation splice).
- ✅ Uses an API provider (default: ElevenLabs Music) so you don't need a GPU.
- ✅ Keeps an audit trail (prompt/params/model/version/time) in SQLite for debugging.
- ❌ Not a full production multi-tenant system (no auth, no quotas, single-process assumption).
- ❌ "Extend / inpaint / stems" are not implemented unless your provider supports them.

## Requirements

- Windows + PowerShell
- Python 3.10+ (works with 3.14)
- An ElevenLabs API key with Music enabled

## Quick start (no dependencies, recommended)

This mode uses only the Python standard library (no `pip install` needed).

1) Set env vars (PowerShell):

```powershell
$env:ELEVENLABS_API_KEY="YOUR_KEY_HERE"
```

Optional:

```powershell
$env:AI_MUSIC_DATA_DIR="C:\Users\Administrator\Documents\Playground\ai-music-tool\data"
$env:AI_MUSIC_OUTPUT_FORMAT="mp3_192kbps"
```

2) Run:

```powershell
cd C:\Users\Administrator\Documents\Playground\ai-music-tool
python .\backend\stdlib_server.py
```

3) Open:

- http://127.0.0.1:8000

## Documentation

- Usage guide: `docs\USAGE.md`
- Configuration: `docs\CONFIG.md`
- Architecture: `docs\ARCH.md`

## FastAPI mode (optional)

If you prefer FastAPI (nicer docs, async), install deps and run `backend\main.py`:

```powershell
python -m pip install -r .\backend\requirements.txt
python .\backend\main.py
```

### Fix for pip PermissionError on this machine (Python 3.14)

If `pip install` fails with errors like:

- `Permission denied: ...\\pip-unpack-...\\*.whl.metadata`
- or `ensurepip` fails when creating a venv

This environment can create non-writable temp directories when Python uses restrictive
directory modes. Use the provided opt-in startup patch (via `PYTHONPATH`) and install helper:

```powershell
cd C:\Users\Administrator\Documents\Playground\ai-music-tool
.\tools\pip_install_backend.ps1
```

Under the hood this sets:

- `PYTHONPATH=...\tools\py314_tempfile_fix` (loads `sitecustomize.py`)
- `PY_TEMP_BASE=...\ .tmp_python` (a writable temp base inside the project)
- Installs with `--prefer-binary` and `--only-binary=pydantic-core,jiter` to avoid Rust source builds on Python 3.14

Quick verification (optional):

```powershell
cd C:\Users\Administrator\Documents\Playground\ai-music-tool
$env:PYTHONPATH="$PWD\tools\py314_tempfile_fix"
$env:PY_TEMP_BASE="$PWD\.tmp_python"
python -c "import tempfile, pathlib; d=tempfile.mkdtemp(prefix='pip-'); pathlib.Path(d,'x.txt').write_text('ok',encoding='utf-8'); print('ok', d)"
```

## Notes on "singing / vocals"

The ElevenLabs API supports both instrumental and vocal tracks. This tool exposes a `Vocals` toggle:

- `Vocals=On` sets `force_instrumental=false` and also nudges the prompt to request singing.
- `Vocals=Off` sets `force_instrumental=true` (instrumental-only).

Even with vocals enabled, results can vary by prompt. The UI includes a "lyrics" box; if you provide lyrics, the backend will inject them into the prompt text.

## Notes on "Extend"

ElevenLabs Music API (as integrated here) doesn't provide a dedicated “extend this exact audio” endpoint. This tool implements **Extend** by generating a **new, longer** track using the same prompt/params (best-effort continuity).

## File layout

- `backend\main.py`: FastAPI app + routes
- `backend\stdlib_server.py`: no-deps HTTP server (recommended)
- `backend\providers\elevenlabs.py`: ElevenLabs Music provider
- `backend\providers\elevenlabs_stdlib.py`: ElevenLabs provider (stdlib-only)
- `backend\storage.py`: SQLite job store
- `backend\static\index.html`: single-page UI
- `data\`: SQLite DB + generated audio files (created on first run)
