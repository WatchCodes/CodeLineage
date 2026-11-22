from __future__ import annotations

import subprocess
from unittest import mock

import pytest

from codelineage.contracts import is_valid, validate
from codelineage.lineage import build_repository_mapping, mapping_from_migration_report
from codelineage.probes import repo_exists, verify_mapping


def lineage_report(**overrides):
    """Report shape consumed by lineage.py."""
    doc = {
        "schema_version": 1,
        "batch_id": "b1",
        "source": "Owner/Repo",
        "destination": "WatchCodes/nastech-repo",
        "sha": "a" * 40,
        "status": "VERIFIED",
        "license": "MIT",
        "generated_at": "2026-11-22T00:00:00Z",
    }
    doc.update(overrides)
    return doc


def schema_migration_report(**overrides):
    """Schema-valid MigrationReport."""
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


# --- lineage + contracts integration ---


def test_build_repository_mapping_is_schema_valid():
    mapping = build_repository_mapping(
        source="Owner/Repo",
        destination="WatchCodes/nastech-repo",
        sha="a" * 40,
        license="MIT",
        status="VERIFIED",
        verified_at="2026-11-22T00:00:00Z",
    )
    ok, errors = is_valid("repository-mapping", mapping)
    assert ok, errors
    assert mapping["schema_version"] == 1


def test_mapping_from_migration_report_round_trip():
    report = lineage_report()
    mapping = mapping_from_migration_report(report)
    validate("repository-mapping", mapping)
    assert mapping["source"] == report["source"]
    assert mapping["destination"] == report["destination"]
    assert mapping["sha"] == report["sha"]
    assert mapping["status"] == report["status"]
    assert mapping["verified_at"] == report["generated_at"]


def test_mapping_from_migration_report_uses_report_sha():
    report = lineage_report(sha="c" * 40)
    mapping = mapping_from_migration_report(report)
    assert mapping["sha"] == "c" * 40
    validate("repository-mapping", mapping)


def test_mapping_from_migration_report_license_fallback():
    report = lineage_report(license=None)
    mapping = mapping_from_migration_report(report)
    assert mapping["license"] == "NOASSERTION"
    validate("repository-mapping", mapping)


def test_build_repository_mapping_rejects_invalid_sha():
    with pytest.raises(Exception):
        build_repository_mapping(
            source="Owner/Repo",
            destination="WatchCodes/nastech-repo",
            sha="not-a-sha",
            license="MIT",
            status="VERIFIED",
            verified_at="2026-11-22T00:00:00Z",
        )


def test_build_repository_mapping_rejects_invalid_status():
    with pytest.raises(Exception):
        build_repository_mapping(
            source="Owner/Repo",
            destination="WatchCodes/nastech-repo",
            sha="a" * 40,
            license="MIT",
            status="NOT_A_STATUS",
            verified_at="2026-11-22T00:00:00Z",
        )


def test_schema_migration_report_validates():
    report = schema_migration_report()
    ok, errors = is_valid("migration-report", report)
    assert ok, errors


# --- probes integration ---


def test_repo_exists_true_on_zero_returncode():
    cp = subprocess.CompletedProcess(args=["gh"], returncode=0, stdout="{}", stderr="")
    with mock.patch("codelineage.probes._run", return_value=cp) as run_mock:
        assert repo_exists("WatchCodes/nastech-repo") is True
        run_mock.assert_called_once()


def test_repo_exists_false_on_nonzero_returncode():
    cp = subprocess.CompletedProcess(args=["gh"], returncode=1, stdout="", stderr="not found")
    with mock.patch("codelineage.probes._run", return_value=cp):
        assert repo_exists("WatchCodes/nastech-repo") is False


def test_verify_mapping_checks_repo_field():
    mapping = {
        "source": "Owner/Repo",
        "repo": "WatchCodes/nastech-repo",
        "sha": "a" * 40,
    }
    cp = subprocess.CompletedProcess(args=["gh"], returncode=0, stdout="{}", stderr="")
    with mock.patch("codelineage.probes._run", return_value=cp):
        result = verify_mapping(mapping)
    assert result["checks"]["repo_exists"] is True
    assert result["checks"]["destination_exists"] is True
    assert result["ok"] is True


def test_verify_mapping_fails_when_repo_missing():
    mapping = {
        "source": "Owner/Repo",
        "destination": "WatchCodes/nastech-repo",
    }
    result = verify_mapping(mapping)
    assert result["checks"]["repo_exists"] is False
    assert result["ok"] is False


def test_verify_mapping_fails_when_repo_probe_fails():
    mapping = {
        "source": "Owner/Repo",
        "repo": "WatchCodes/nastech-repo",
    }
    cp = subprocess.CompletedProcess(args=["gh"], returncode=1, stdout="", stderr="no")
    with mock.patch("codelineage.probes._run", return_value=cp):
        result = verify_mapping(mapping)
    assert result["ok"] is False
    assert result["checks"]["repo_exists"] is False


# --- end-to-end lineage flow ---


def test_report_to_mapping_to_probe_flow():
    report = lineage_report()
    mapping = mapping_from_migration_report(report)
    validate("repository-mapping", mapping)

    probe_input = dict(mapping)
    probe_input["repo"] = mapping["destination"]
    cp = subprocess.CompletedProcess(args=["gh"], returncode=0, stdout="{}", stderr="")
    with mock.patch("codelineage.probes._run", return_value=cp):
        result = verify_mapping(probe_input)
    assert result["ok"] is True
    assert result["mapping"]["source"] == "Owner/Repo"
    assert result["mapping"]["destination"] == "WatchCodes/nastech-repo"
