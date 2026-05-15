from __future__ import annotations

import json
import os
from pathlib import Path

import test_env  # noqa: F401


JsonSchema = dict[str, object]


def _assert_schema(value: object, schema: JsonSchema, *, path: str = "$") -> None:
    expected_type = schema.get("type")
    if expected_type == "object":
        assert isinstance(value, dict), f"{path} should be object"
        required = schema.get("required") or []
        assert isinstance(required, list)
        for key in required:
            assert key in value, f"{path}.{key} missing"
        properties = schema.get("properties") or {}
        assert isinstance(properties, dict)
        for key, child_schema in properties.items():
            if key in value:
                assert isinstance(child_schema, dict)
                _assert_schema(value[key], child_schema, path=f"{path}.{key}")
        return
    if expected_type == "array":
        assert isinstance(value, list), f"{path} should be array"
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for idx, item in enumerate(value):
                _assert_schema(item, item_schema, path=f"{path}[{idx}]")
        return
    if expected_type == "string":
        assert isinstance(value, str), f"{path} should be string"
        return
    if expected_type == "integer":
        assert isinstance(value, int), f"{path} should be integer"
        return
    if expected_type == "boolean":
        assert isinstance(value, bool), f"{path} should be boolean"
        return
    if isinstance(expected_type, list):
        if "null" in expected_type and value is None:
            return
        non_null = [t for t in expected_type if t != "null"]
        if non_null:
            _assert_schema(value, {**schema, "type": non_null[0]}, path=path)


PUBLIC_USER_SCHEMA: JsonSchema = {
    "type": "object",
    "required": ["id", "username", "role", "daily_quota", "disabled", "quota"],
    "properties": {
        "id": {"type": "integer"},
        "username": {"type": "string"},
        "role": {"type": "string"},
        "daily_quota": {"type": "integer"},
        "disabled": {"type": "boolean"},
        "quota": {
            "type": "object",
            "required": ["date", "used", "limit", "remaining"],
            "properties": {
                "date": {"type": "string"},
                "used": {"type": "integer"},
                "limit": {"type": "integer"},
                "remaining": {"type": "integer"},
            },
        },
    },
}


JOB_SCHEMA: JsonSchema = {
    "type": "object",
    "required": [
        "job_id",
        "status",
        "created_at_ms",
        "updated_at_ms",
        "provider",
        "prompt",
        "params",
        "visibility",
        "share_permission",
    ],
    "properties": {
        "job_id": {"type": "string"},
        "status": {"type": "string"},
        "created_at_ms": {"type": "integer"},
        "updated_at_ms": {"type": "integer"},
        "provider": {"type": "string"},
        "prompt": {"type": "string"},
        "params": {"type": "object"},
        "visibility": {"type": "string"},
        "share_permission": {"type": "string"},
    },
}


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


def test_key_endpoint_response_bodies_match_json_contracts(client, auth_headers, factories) -> None:
    me = client.get("/api/auth/me", headers=auth_headers)
    assert me.status_code == 200, me.text
    _assert_schema(me.json(), {"type": "object", "required": ["user"], "properties": {"user": PUBLIC_USER_SCHEMA}})

    providers = client.get("/api/providers", headers=auth_headers)
    assert providers.status_code == 200, providers.text
    _assert_schema(
        providers.json(),
        {
            "type": "object",
            "required": ["providers", "default_provider"],
            "properties": {
                "providers": {"type": "array", "items": {"type": "object"}},
                "default_provider": {"type": "string"},
            },
        },
    )

    job_id = factories.create_succeeded_job(prompt="contract", duration_sec=5)
    job = client.get(f"/api/jobs/{job_id}", headers=auth_headers)
    assert job.status_code == 200, job.text
    _assert_schema(job.json(), JOB_SCHEMA)

    history = client.get("/api/jobs/history?offset=0&limit=10", headers=auth_headers)
    assert history.status_code == 200, history.text
    _assert_schema(
        history.json(),
        {
            "type": "object",
            "required": ["jobs", "total", "offset", "limit"],
            "properties": {
                "jobs": {"type": "array", "items": JOB_SCHEMA},
                "total": {"type": "integer"},
                "offset": {"type": "integer"},
                "limit": {"type": "integer"},
            },
        },
    )
