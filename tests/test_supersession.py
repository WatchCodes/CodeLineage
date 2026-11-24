"""Supersession keeps mapping history and never grants stale rewrite authority.

RepositoryMapping.schema.json already defines ``superseded_by`` and README.md
promises that superseded mappings are marked, not removed. The store must keep
the old evidence and let consumers read only the active mapping by default.
"""
from __future__ import annotations

import json

from tests.test_contracts_cli import run_cli, valid_mapping, valid_probe


def _record(tmp_path, store, mapping, *, name: str = "mapping"):
    mapping_path = tmp_path / f"{name}.json"
    probe_path = tmp_path / f"{name}-probe.json"
    mapping_path.write_text(json.dumps(mapping), encoding="utf-8")
    probe_path.write_text(json.dumps(valid_probe(mapping)), encoding="utf-8")
    return run_cli(
        [
            "record",
            "--mapping",
            str(mapping_path),
            "--probe-record",
            str(probe_path),
            "--store",
            str(store),
        ],
        cwd=tmp_path,
    )


def _lookup(tmp_path, store, *, source: str, include_superseded: bool = False):
    args = ["lookup", "--store", str(store), "--source", source]
    if include_superseded:
        args.append("--include-superseded")
    return run_cli(args, cwd=tmp_path)


def test_same_destination_supersedes_prior_evidence_without_deletion(tmp_path):
    store = tmp_path / "store.json"
    first = valid_mapping(verified_at="2026-11-22T00:00:00Z", sha="a" * 40)
    second = valid_mapping(verified_at="2026-11-23T00:00:00Z", sha="b" * 40)

    assert _record(tmp_path, store, first, name="first").returncode == 0
    result = _record(tmp_path, store, second, name="second")
    assert result.returncode == 0, result.stdout + result.stderr

    payload = json.loads(result.stdout)
    assert payload["action"] == "updated"
    assert payload["superseded"] == [first["destination"]]

    mappings = json.loads(store.read_text(encoding="utf-8"))["mappings"]
    assert len(mappings) == 2
    old = next(m for m in mappings if m["verified_at"] == first["verified_at"])
    assert old["sha"] == first["sha"]
    assert old["superseded_by"] == second["destination"]
    active = next(m for m in mappings if "superseded_by" not in m)
    assert active["verified_at"] == second["verified_at"]
    assert active["sha"] == second["sha"]


def test_new_destination_supersedes_previous_source_mapping(tmp_path):
    store = tmp_path / "store.json"
    old = valid_mapping(destination="WatchCodes/nastech-old", verified_at="2026-11-22T00:00:00Z")
    new = valid_mapping(destination="WatchCodes/nastech-new", verified_at="2026-11-23T00:00:00Z")

    assert _record(tmp_path, store, old, name="old").returncode == 0
    assert _record(tmp_path, store, new, name="new").returncode == 0

    active = _lookup(tmp_path, store, source="Owner/Repo")
    assert active.returncode == 0, active.stdout + active.stderr
    active_doc = json.loads(active.stdout)
    assert active_doc["count"] == 1
    assert active_doc["mappings"][0]["destination"] == new["destination"]

    audit = _lookup(tmp_path, store, source="Owner/Repo", include_superseded=True)
    assert audit.returncode == 0
    audit_doc = json.loads(audit.stdout)
    assert audit_doc["count"] == 2
    assert {m["destination"] for m in audit_doc["mappings"]} == {
        old["destination"],
        new["destination"],
    }
    assert next(m for m in audit_doc["mappings"] if m["destination"] == old["destination"])[
        "superseded_by"
    ] == new["destination"]


def test_exact_duplicate_record_is_idempotent(tmp_path):
    store = tmp_path / "store.json"
    mapping = valid_mapping()

    assert _record(tmp_path, store, mapping, name="first").returncode == 0
    second = _record(tmp_path, store, mapping, name="duplicate")
    assert second.returncode == 0, second.stdout + second.stderr

    payload = json.loads(second.stdout)
    assert payload["action"] == "unchanged"
    assert payload["superseded"] == []
    mappings = json.loads(store.read_text(encoding="utf-8"))["mappings"]
    assert mappings == [mapping]


def test_older_evidence_cannot_reactivate_superseded_mapping(tmp_path):
    store = tmp_path / "store.json"
    new = valid_mapping(verified_at="2026-11-23T00:00:00Z", sha="b" * 40)
    old = valid_mapping(verified_at="2026-11-22T00:00:00Z", sha="a" * 40)

    assert _record(tmp_path, store, new, name="new").returncode == 0
    result = _record(tmp_path, store, old, name="old")
    assert result.returncode == 1
    assert "older" in json.loads(result.stdout)["error"].lower()

    mappings = json.loads(store.read_text(encoding="utf-8"))["mappings"]
    assert mappings == [new]
