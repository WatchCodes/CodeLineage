from __future__ import annotations

import subprocess

import pytest

from codelineage.lineage import build_repository_mapping, mapping_from_migration_report
from codelineage.probes import PROBE_KIND, PROBE_SCHEMA_VERSION, repo_exists, verify_mapping


def _report(**overrides):
    report = {
        "schema_version": 1,
        "batch_id": "b1",
        "source": "Owner/Repo",
        "destination": "WatchCodes/nastech-repo",
        "sha": "A" * 40,
        "status": "VERIFIED",
        "license": "MIT",
        "generated_at": "2026-11-22T00:00:00Z",
    }
    report.update(overrides)
    return report


def _mapping(**overrides):
    mapping = {
        "schema_version": 1,
        "source": "Owner/Repo",
        "destination": "WatchCodes/nastech-repo",
        "sha": "a" * 40,
        "license": "MIT",
        "status": "VERIFIED",
        "verified_at": "2026-11-22T00:00:00Z",
    }
    mapping.update(overrides)
    return mapping


def test_build_repository_mapping_is_deterministic_and_idempotent():
    kwargs = dict(
        source="Owner/Repo",
        destination="WatchCodes/nastech-repo",
        sha="A" * 40,
        license="MIT",
        status="VERIFIED",
        verified_at="2026-11-22T00:00:00Z",
    )
    first = build_repository_mapping(**kwargs)
    second = build_repository_mapping(**kwargs)
    assert first == second
    assert first["sha"] == "a" * 40


def test_build_repository_mapping_requires_verified_at_fail_closed():
    with pytest.raises(ValueError, match="verified_at must be provided"):
        build_repository_mapping(
            source="Owner/Repo",
            destination="WatchCodes/nastech-repo",
            sha="a" * 40,
            license="MIT",
            status="VERIFIED",
            verified_at=None,
        )


def test_build_repository_mapping_rejects_empty_required_fields():
    with pytest.raises(ValueError, match="source must be a non-empty string"):
        build_repository_mapping(
            source="  ",
            destination="WatchCodes/nastech-repo",
            sha="a" * 40,
            license="MIT",
            status="VERIFIED",
            verified_at="2026-11-22T00:00:00Z",
        )


def test_mapping_from_migration_report_is_deterministic_and_fail_closed():
    report = _report()
    first = mapping_from_migration_report(report)
    second = mapping_from_migration_report(report)
    assert first == second
    assert first["verified_at"] == "2026-11-22T00:00:00Z"

    with pytest.raises(ValueError, match="missing required fields"):
        mapping_from_migration_report({"source": "Owner/Repo"})

    with pytest.raises(ValueError, match="verified_at or generated_at"):
        mapping_from_migration_report(
            {
                "source": "Owner/Repo",
                "destination": "WatchCodes/nastech-repo",
                "sha": "a" * 40,
                "status": "VERIFIED",
                "license": "MIT",
            }
        )


def test_mapping_from_migration_report_rejects_non_mapping():
    with pytest.raises(ValueError, match="report must be a mapping"):
        mapping_from_migration_report(["not", "a", "mapping"])  # type: ignore[arg-type]


def test_probe_record_is_schema_shaped_and_deterministic(monkeypatch):
    monkeypatch.setattr("codelineage.probes.shutil.which", lambda _: "/usr/bin/gh")
    monkeypatch.setattr(
        "codelineage.probes._run",
        lambda cmd, timeout=30: subprocess.CompletedProcess(cmd, 0, stdout='{"name":"nastech-repo"}', stderr=""),
    )

    mapping = _mapping()
    first = verify_mapping(mapping)
    second = verify_mapping(mapping)

    assert first == second
    assert first["schema_version"] == PROBE_SCHEMA_VERSION
    assert first["kind"] == PROBE_KIND
    assert first["mapping"] == {
        "source": "Owner/Repo",
        "destination": "WatchCodes/nastech-repo",
        "sha": "a" * 40,
    }
    assert first["checks"]["destination_exists"] is True
    assert first["checks"]["repo_exists"] is True
    assert first["errors"] == []
    assert first["ok"] is True


def test_probe_is_fail_closed_when_gh_missing(monkeypatch):
    def missing_gh(cmd, timeout=30):
        raise FileNotFoundError("gh")

    monkeypatch.setattr("codelineage.probes._run", missing_gh)
    record = verify_mapping(_mapping())

    assert record["ok"] is False
    assert record["checks"]["destination_exists"] is False
    assert "gh CLI unavailable" in record["errors"]


def test_probe_is_fail_closed_on_missing_destination(monkeypatch):
    monkeypatch.setattr("codelineage.probes.shutil.which", lambda _: "/usr/bin/gh")
    record = verify_mapping({"source": "Owner/Repo", "sha": "a" * 40})

    assert record["ok"] is False
    assert record["checks"]["destination_exists"] is False
    assert "missing destination" in record["errors"]


def test_probe_is_fail_closed_on_lookup_failure(monkeypatch):
    monkeypatch.setattr("codelineage.probes.shutil.which", lambda _: "/usr/bin/gh")

    def boom(cmd, timeout=30):
        raise RuntimeError("network down")

    monkeypatch.setattr("codelineage.probes._run", boom)
    record = verify_mapping(_mapping())

    assert record["ok"] is False
    assert record["checks"]["destination_exists"] is False
    assert any("RuntimeError" in err for err in record["errors"])


def test_probe_is_fail_closed_on_timeout(monkeypatch):
    monkeypatch.setattr("codelineage.probes.shutil.which", lambda _: "/usr/bin/gh")

    def slow(cmd, timeout=30):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=timeout)

    monkeypatch.setattr("codelineage.probes._run", slow)
    record = verify_mapping(_mapping())

    assert record["ok"] is False
    assert record["checks"]["destination_exists"] is False
    assert any("timed out" in err for err in record["errors"])


def test_probe_rejects_non_mapping_input():
    with pytest.raises(ValueError, match="mapping must be a mapping"):
        verify_mapping("not-a-mapping")  # type: ignore[arg-type]


def test_repo_exists_is_fail_closed(monkeypatch):
    monkeypatch.setattr("codelineage.probes.shutil.which", lambda _: None)
    assert repo_exists("WatchCodes/nastech-repo") is False

    monkeypatch.setattr("codelineage.probes.shutil.which", lambda _: "/usr/bin/gh")

    def boom(cmd, timeout=30):
        raise OSError("boom")

    monkeypatch.setattr("codelineage.probes._run", boom)
    assert repo_exists("WatchCodes/nastech-repo") is False


def test_records_have_no_attribution_hints(monkeypatch):
    monkeypatch.setattr("codelineage.probes.shutil.which", lambda _: "/usr/bin/gh")
    monkeypatch.setattr(
        "codelineage.probes._run",
        lambda cmd, timeout=30: subprocess.CompletedProcess(cmd, 0, stdout="{}", stderr=""),
    )
    mapping = build_repository_mapping(
        source="Owner/Repo",
        destination="WatchCodes/nastech-repo",
        sha="a" * 40,
        license="MIT",
        status="VERIFIED",
        verified_at="2026-11-22T00:00:00Z",
    )
    probe = verify_mapping(mapping)

    forbidden = {"author", "authored_by", "committer", "attribution", "credit", "credits"}
    assert forbidden.isdisjoint(mapping.keys())
    assert forbidden.isdisjoint(probe.keys())
    assert forbidden.isdisjoint(probe["mapping"].keys())
