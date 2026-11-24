"""Regression tests: a bare status claim is not proof of a verified mapping.

CodeLineage is the authority that grants URL-rewrite permission (plan section
9). Recording a mapping from a report whose checks all failed, or from a
mapping with no probe artifact, silently grants that authority. These tests
pin the evidence requirement at the CLI boundary.
"""
from __future__ import annotations

import json

from tests.test_contracts_cli import run_cli, valid_mapping, valid_migration_report


def _write(path, document):
    path.write_text(json.dumps(document), encoding="utf-8")
    return str(path)


def _probe(mapping, *, fields=None, **overrides):
    probed = {
        "source": mapping["source"],
        "destination": mapping["destination"],
        "sha": mapping["sha"],
    }
    if fields is not None:
        probed.update(fields)
    record = {
        "schema_version": 1,
        "kind": "verification-probe",
        "mapping": probed,
        "checks": {"destination_exists": True, "repo_exists": True},
        "errors": [],
        "ok": True,
    }
    record.update(overrides)
    return record


def test_record_rejects_report_with_all_checks_false(tmp_path):
    store = tmp_path / "store.json"
    report = valid_migration_report(
        checks={key: False for key in valid_migration_report()["checks"]},
        error="verification never ran",
    )
    path = _write(tmp_path / "report.json", report)
    result = run_cli(["record", "--report", path, "--store", str(store)], cwd=tmp_path)
    assert result.returncode == 1
    assert json.loads(result.stdout)["ok"] is False
    assert not store.exists()


def test_record_rejects_report_with_one_false_check(tmp_path):
    store = tmp_path / "store.json"
    checks = valid_migration_report()["checks"]
    checks = dict(checks, gated=False)
    path = _write(tmp_path / "report.json", valid_migration_report(checks=checks))
    result = run_cli(["record", "--report", path, "--store", str(store)], cwd=tmp_path)
    assert result.returncode == 1
    assert "gated" in json.loads(result.stdout)["error"]


def test_record_rejects_report_that_declares_an_error(tmp_path):
    store = tmp_path / "store.json"
    report = valid_migration_report(error="verification never completed")
    path = _write(tmp_path / "report.json", report)
    result = run_cli(["record", "--report", path, "--store", str(store)], cwd=tmp_path)
    assert result.returncode == 1
    assert "failed report" in json.loads(result.stdout)["error"]
    assert not store.exists()


def test_record_accepts_report_with_full_evidence(tmp_path):
    store = tmp_path / "store.json"
    report = valid_migration_report()
    report["receipt"]["checkpoints"] = [
        {"stage": "report", "at": "2026-11-24T00:00:00Z", "ok": True}
    ]
    path = _write(tmp_path / "report.json", report)
    result = run_cli(["record", "--report", path, "--store", str(store)], cwd=tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["action"] == "created"


def test_record_rejects_bare_mapping_without_probe_evidence(tmp_path):
    store = tmp_path / "store.json"
    path = _write(tmp_path / "mapping.json", valid_mapping())
    result = run_cli(["record", "--mapping", path, "--store", str(store)], cwd=tmp_path)
    assert result.returncode == 1
    assert "probe" in json.loads(result.stdout)["error"].lower()
    assert not store.exists()


def test_record_rejects_probe_identity_mismatch(tmp_path):
    store = tmp_path / "store.json"
    mapping = valid_mapping()
    probe = _probe(mapping, fields={"sha": "b" * 40})
    mapping_path = _write(tmp_path / "mapping.json", mapping)
    probe_path = _write(tmp_path / "probe.json", probe)
    result = run_cli(
        ["record", "--mapping", mapping_path, "--probe-record", probe_path, "--store", str(store)],
        cwd=tmp_path,
    )
    assert result.returncode == 1
    assert "mismatch" in json.loads(result.stdout)["error"].lower()
    assert not store.exists()


def test_record_accepts_mapping_with_matching_probe_evidence(tmp_path):
    store = tmp_path / "store.json"
    mapping = valid_mapping()
    mapping_path = _write(tmp_path / "mapping.json", mapping)
    probe_path = _write(tmp_path / "probe.json", _probe(mapping))
    result = run_cli(
        ["record", "--mapping", mapping_path, "--probe-record", probe_path, "--store", str(store)],
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["action"] == "created"
