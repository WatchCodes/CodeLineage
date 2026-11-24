from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from codelineage.contracts import (
    ContractError,
    is_valid,
    known_schema_names,
    load_schema,
    schemas_dir,
    validate,
    validate_file,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def run_cli(args: list[str], cwd: Path | None = None, env_extra: dict[str, str] | None = None):
    env = dict(os.environ)
    pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(REPO_ROOT) + (":" + pp if pp else "")
    if env_extra:
        env.update(env_extra)
    cmd = [sys.executable, "-m", "codelineage.cli", *args]
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, env=env)


def valid_mapping(**overrides):
    doc = {
        "schema_version": 1,
        "source": "Owner/Repo",
        "destination": "WatchCodes/nastech-repo",
        "sha": "a" * 40,
        "license": "MIT",
        "status": "VERIFIED",
        "verified_at": "2026-11-22T00:00:00Z",
    }
    doc.update(overrides)
    return doc


def valid_probe(mapping, **overrides):
    record = {
        "schema_version": 1,
        "kind": "verification-probe",
        "mapping": {
            "source": mapping["source"],
            "destination": mapping["destination"],
            "sha": mapping["sha"],
        },
        "checks": {"destination_exists": True, "repo_exists": True},
        "errors": [],
        "ok": True,
    }
    record.update(overrides)
    return record


def valid_migration_report(**overrides):
    doc = {
        "schema_version": 1,
        "batch_id": "b1",
        "source": "Owner/Repo",
        "destination": "WatchCodes/nastech-repo",
        "status": "VERIFIED",
        "checks": {
            "created": True,
            "named": True,
            "owned": True,
            "gated": True,
            "license_kept": True,
            "credits": True,
        },
        "receipt": {
            "idempotency_key": "b1::Owner/Repo",
            "destination_repo_id": 1,
            "source_sha": "a" * 40,
            "destination_sha": "b" * 40,
            "checkpoints": [],
        },
        "license": {"detected": "MIT", "preserved": True},
        "attribution": {"notice": True, "credits": True},
        "error": None,
    }
    doc.update(overrides)
    return doc


# --- contracts ---


def test_known_schema_names_include_repository_mapping():
    names = known_schema_names()
    assert "repository-mapping" in names
    assert "migration-report" in names
    assert "common" not in names


def test_schemas_dir_exists():
    p = schemas_dir()
    assert p.is_dir()
    assert (p / "repository-mapping.schema.json").is_file()


def test_load_schema_unknown_fails_closed():
    with pytest.raises(ContractError):
        load_schema("not-a-schema")


def test_validate_repository_mapping_ok():
    validate("repository-mapping", valid_mapping())


def test_validate_repository_mapping_rejects_missing_required():
    doc = valid_mapping()
    del doc["source"]
    ok, errors = is_valid("repository-mapping", doc)
    assert not ok
    assert errors


def test_validate_repository_mapping_rejects_additional_property():
    doc = valid_mapping()
    doc["unexpected"] = True
    ok, errors = is_valid("repository-mapping", doc)
    assert not ok
    assert any("additional" in e.lower() or "unexpected" in e for e in errors)


def test_validate_unknown_schema_fails_closed():
    ok, errors = is_valid("nope-schema", {"schema_version": 1})
    assert not ok
    assert errors


def test_validate_file_missing_fails_closed(tmp_path):
    ok, errors = validate_file("repository-mapping", tmp_path / "missing.json")
    assert not ok
    assert any("not found" in e.lower() for e in errors)


def test_validate_file_invalid_json_fails_closed(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{", encoding="utf-8")
    ok, errors = validate_file("repository-mapping", p)
    assert not ok
    assert any("invalid json" in e.lower() for e in errors)


def test_validate_file_valid(tmp_path):
    p = tmp_path / "mapping.json"
    p.write_text(json.dumps(valid_mapping()), encoding="utf-8")
    ok, errors = validate_file("repository-mapping", p)
    assert ok, errors


def test_missing_schemas_dir_fails_closed(tmp_path):
    bad_dir = tmp_path / "nope"
    f = tmp_path / "mapping.json"
    f.write_text(json.dumps(valid_mapping()), encoding="utf-8")
    r = run_cli(
        ["validate", "--schema", "repository-mapping", "--file", str(f)],
        cwd=tmp_path,
        env_extra={"WATCHCODES_SCHEMAS_DIR": str(bad_dir)},
    )
    assert r.returncode == 1
    out = r.stdout + r.stderr
    assert "schemas directory not found" in out


# --- CLI validate ---


def test_cli_validate_ok(tmp_path):
    f = tmp_path / "mapping.json"
    f.write_text(json.dumps(valid_mapping()), encoding="utf-8")
    r = run_cli(["validate", "--schema", "repository-mapping", "--file", str(f)], cwd=tmp_path)
    assert r.returncode == 0
    assert "OK" in r.stdout


def test_cli_validate_bad_exit_1(tmp_path):
    f = tmp_path / "mapping.json"
    f.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
    r = run_cli(["validate", "--schema", "repository-mapping", "--file", str(f)], cwd=tmp_path)
    assert r.returncode == 1


def test_cli_validate_missing_file_exit_1(tmp_path):
    r = run_cli(["validate", "--schema", "repository-mapping", "--file", str(tmp_path / "nope.json")], cwd=tmp_path)
    assert r.returncode == 1


def test_cli_validate_json_output(tmp_path):
    f = tmp_path / "mapping.json"
    f.write_text(json.dumps(valid_mapping()), encoding="utf-8")
    r = run_cli(["validate", "--schema", "repository-mapping", "--file", str(f), "--json"], cwd=tmp_path)
    assert r.returncode == 0
    payload = json.loads(r.stdout)
    assert payload["ok"] is True
    assert payload["schema"] == "repository-mapping"


def test_cli_validate_json_output_bad(tmp_path):
    f = tmp_path / "mapping.json"
    f.write_text(json.dumps({}), encoding="utf-8")
    r = run_cli(["validate", "--schema", "repository-mapping", "--file", str(f), "--json"], cwd=tmp_path)
    assert r.returncode == 1
    payload = json.loads(r.stdout)
    assert payload["ok"] is False
    assert payload["errors"]


# --- CLI record / lookup ---


def test_cli_record_and_lookup_mapping(tmp_path):
    store = tmp_path / "store.json"
    mapping = tmp_path / "mapping.json"
    document = valid_mapping()
    mapping.write_text(json.dumps(document), encoding="utf-8")
    probe = tmp_path / "probe.json"
    probe.write_text(json.dumps(valid_probe(document)), encoding="utf-8")
    r = run_cli(
        ["record", "--mapping", str(mapping), "--probe-record", str(probe), "--store", str(store)],
        cwd=tmp_path,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    payload = json.loads(r.stdout)
    assert payload["ok"] is True
    assert payload["action"] == "created"
    assert payload["mapping"]["destination"] == "WatchCodes/nastech-repo"

    r2 = run_cli(["lookup", "--store", str(store), "--source", "Owner/Repo"], cwd=tmp_path)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    found = json.loads(r2.stdout)
    assert found["count"] == 1
    assert found["mappings"][0]["destination"] == "WatchCodes/nastech-repo"


def test_cli_record_from_report(tmp_path):
    store = tmp_path / "store.json"
    report = tmp_path / "report.json"
    report.write_text(json.dumps(valid_migration_report()), encoding="utf-8")
    r = run_cli(["record", "--report", str(report), "--store", str(store)], cwd=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    payload = json.loads(r.stdout)
    assert payload["mapping"]["status"] == "VERIFIED"


def test_cli_record_rejects_unverified(tmp_path):
    store = tmp_path / "store.json"
    mapping = tmp_path / "mapping.json"
    document = valid_mapping(status="FAILED")
    mapping.write_text(json.dumps(document), encoding="utf-8")
    probe = tmp_path / "probe.json"
    probe.write_text(json.dumps(valid_probe(document)), encoding="utf-8")
    r = run_cli(
        ["record", "--mapping", str(mapping), "--probe-record", str(probe), "--store", str(store)],
        cwd=tmp_path,
    )
    assert r.returncode == 1
    payload = json.loads(r.stdout)
    assert payload["ok"] is False
    assert "unverified" in payload["error"].lower() or "FAILED" in payload["error"]


def test_cli_lookup_not_found_exit_1(tmp_path):
    store = tmp_path / "store.json"
    store.write_text(json.dumps({"schema_version": 1, "mappings": [valid_mapping()]}), encoding="utf-8")
    r = run_cli(["lookup", "--store", str(store), "--source", "Nobody/Nope"], cwd=tmp_path)
    assert r.returncode == 1
    payload = json.loads(r.stdout)
    assert payload["ok"] is False
    assert payload["count"] == 0


def test_cli_record_updates_existing(tmp_path):
    store = tmp_path / "store.json"
    m1 = tmp_path / "m1.json"
    m2 = tmp_path / "m2.json"
    first = valid_mapping(verified_at="2026-11-22T00:00:00Z")
    second = valid_mapping(verified_at="2026-11-23T00:00:00Z")
    m1.write_text(json.dumps(first), encoding="utf-8")
    m2.write_text(json.dumps(second), encoding="utf-8")
    probe = tmp_path / "probe.json"
    probe.write_text(json.dumps(valid_probe(first)), encoding="utf-8")
    r1 = run_cli(
        ["record", "--mapping", str(m1), "--probe-record", str(probe), "--store", str(store)],
        cwd=tmp_path,
    )
    assert r1.returncode == 0
    r2 = run_cli(
        ["record", "--mapping", str(m2), "--probe-record", str(probe), "--store", str(store)],
        cwd=tmp_path,
    )
    assert r2.returncode == 0
    payload = json.loads(r2.stdout)
    assert payload["action"] == "updated"
    store_doc = json.loads(store.read_text(encoding="utf-8"))
    # Supersession is append-only: old evidence is marked, never deleted.
    assert len(store_doc["mappings"]) == 2
    old = next(m for m in store_doc["mappings"] if m["verified_at"] == first["verified_at"])
    assert old["superseded_by"] == second["destination"]
    active = next(m for m in store_doc["mappings"] if "superseded_by" not in m)
    assert active["verified_at"] == "2026-11-23T00:00:00Z"


def test_cli_record_invalid_report_fails_closed(tmp_path):
    store = tmp_path / "store.json"
    report = tmp_path / "report.json"
    report.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
    r = run_cli(["record", "--report", str(report), "--store", str(store)], cwd=tmp_path)
    assert r.returncode == 1
    payload = json.loads(r.stdout)
    assert payload["ok"] is False


def test_migration_report_accepts_every_codefoundry_checkpoint_stage():
    stages = (
        "start", "validate", "receipt", "scan", "license", "clone",
        "brand", "credits", "gate", "ship", "report",
    )
    checkpoints = [{"stage": s, "at": "2026-11-24T00:00:00Z", "ok": True} for s in stages]
    ok, errors = is_valid("migration-report", valid_migration_report(
        status="REQUIRES_REVIEW",
        receipt={
            "idempotency_key": "b1::Owner/Repo",
            "destination_repo_id": 1,
            "source_sha": "a" * 40,
            "destination_sha": "b" * 40,
            "checkpoints": checkpoints,
        },
    ))
    assert ok, errors


def test_migration_report_still_rejects_unknown_checkpoint_stage():
    checkpoints = [{"stage": "not_a_real_stage", "at": "2026-11-24T00:00:00Z", "ok": True}]
    ok, errors = is_valid("migration-report", valid_migration_report(
        receipt={
            "idempotency_key": "b1::Owner/Repo",
            "destination_repo_id": 1,
            "source_sha": "a" * 40,
            "destination_sha": "b" * 40,
            "checkpoints": checkpoints,
        },
    ))
    assert ok is False
    assert any("not_a_real_stage" in e for e in errors)
