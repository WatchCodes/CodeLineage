"""Regression tests: a probe must not be OK without source and a valid SHA."""
from __future__ import annotations

import subprocess

from codelineage.probes import verify_mapping


def _ok_run(cmd, timeout=30):
    return subprocess.CompletedProcess(cmd, 0, stdout='{"name":"nastech-repo"}', stderr="")


def test_missing_source_and_sha_are_fatal(monkeypatch):
    monkeypatch.setattr("codelineage.probes._run", _ok_run)

    record = verify_mapping({"destination": "WatchCodes/nastech-repo"})

    assert record["ok"] is False
    assert "missing source" in record["errors"]
    assert "missing sha" in record["errors"]
    assert record["checks"]["destination_exists"] is True


def test_missing_source_alone_is_fatal(monkeypatch):
    monkeypatch.setattr("codelineage.probes._run", _ok_run)

    record = verify_mapping({"destination": "WatchCodes/nastech-repo", "sha": "a" * 40})

    assert record["ok"] is False
    assert "missing source" in record["errors"]


def test_malformed_sha_is_fatal(monkeypatch):
    monkeypatch.setattr("codelineage.probes._run", _ok_run)

    record = verify_mapping(
        {"source": "Owner/Repo", "destination": "WatchCodes/nastech-repo", "sha": "abc123"}
    )

    assert record["ok"] is False
    assert any("sha" in err for err in record["errors"])


def test_valid_mapping_with_successful_probe_is_ok(monkeypatch):
    monkeypatch.setattr("codelineage.probes._run", _ok_run)

    record = verify_mapping(
        {"source": "Owner/Repo", "destination": "WatchCodes/nastech-repo", "sha": "a" * 40}
    )

    assert record["ok"] is True
    assert record["errors"] == []
