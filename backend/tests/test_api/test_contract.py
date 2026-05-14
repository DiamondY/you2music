from __future__ import annotations

import json
import os
from pathlib import Path

import test_env  # noqa: F401


def test_openapi_schema_snapshot(client, auth_headers) -> None:
    r = client.get("/openapi.json", headers=auth_headers)
    assert r.status_code == 200, r.text
    schema = r.json()
    assert schema.get("openapi")
    assert schema.get("paths")

    snapshots_dir = Path(__file__).resolve().parent / "snapshots"
    snapshot_path = snapshots_dir / "openapi.json"
    actual = json.dumps(schema, ensure_ascii=False, sort_keys=True, indent=2)

    if str(os.getenv("UPDATE_OPENAPI_SNAPSHOT") or "").strip() == "1":
        snapshots_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(actual + "\n", encoding="utf-8")
        return

    assert snapshot_path.exists(), (
        f"OpenAPI snapshot missing: {snapshot_path}. "
        "Run with UPDATE_OPENAPI_SNAPSHOT=1 once to create it."
    )
    expected = snapshot_path.read_text(encoding="utf-8").strip()
    if actual.strip() != expected.strip():
        snapshots_dir.mkdir(parents=True, exist_ok=True)
        (snapshots_dir / "openapi_actual.json").write_text(actual + "\n", encoding="utf-8")
        raise AssertionError(
            "OpenAPI schema changed! Review diff between openapi.json and openapi_actual.json. "
            "If intentional, update the snapshot. "
            "PowerShell: Copy-Item openapi_actual.json openapi.json -Force"
        )


def test_all_endpoints_have_response_schemas(client, auth_headers) -> None:
    """Every API endpoint should declare at least one non-default response schema."""
    r = client.get("/openapi.json", headers=auth_headers)
    assert r.status_code == 200, r.text
    schema = r.json()
    paths = schema.get("paths") or {}

    missing: list[str] = []
    for path, methods in (paths.items() if isinstance(paths, dict) else []):
        if not isinstance(methods, dict):
            continue
        for method, details in methods.items():
            if str(method).upper() not in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                continue
            if not isinstance(details, dict):
                continue
            responses = details.get("responses")
            if not isinstance(responses, dict):
                missing.append(f"{str(method).upper()} {path}")
                continue
            has_content = any(
                isinstance(resp, dict) and ("content" in resp)
                for code, resp in responses.items()
                if code != "default"
            )
            if not has_content:
                missing.append(f"{str(method).upper()} {path} (no content schema)")

    assert not missing, f"Endpoints missing response schemas: {missing}"
