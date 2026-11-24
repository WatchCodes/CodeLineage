"""The mapping store is the authority for URL-rewrite permission.

Concurrent records must not lose entries, and an older verified mapping must
not replace a newer one. These tests pin those properties at the CLI boundary.
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

from tests.test_contracts_cli import run_cli, valid_mapping, valid_probe


def _write_inputs(tmp_path, index: int, *, verified_at: str = "2026-11-24T00:00:00Z"):
    mapping = valid_mapping(
        source=f"Owner/Repo{index}",
        destination=f"WatchCodes/nastech-repo{index}",
        verified_at=verified_at,
    )
    mapping_path = tmp_path / f"mapping{index}.json"
    probe_path = tmp_path / f"probe{index}.json"
    mapping_path.write_text(json.dumps(mapping), encoding="utf-8")
    probe_path.write_text(json.dumps(valid_probe(mapping)), encoding="utf-8")
    return mapping_path, probe_path


def _record(tmp_path, store, mapping_path, probe_path):
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


def test_concurrent_records_preserve_every_mapping(tmp_path):
    store = tmp_path / "store.json"
    count = 6
    inputs = [_write_inputs(tmp_path, i) for i in range(count)]

    with ThreadPoolExecutor(max_workers=count) as pool:
        futures = [pool.submit(_record, tmp_path, store, m, p) for m, p in inputs]
        for future in futures:
            result = future.result(timeout=20)
            assert result.returncode == 0, result.stdout + result.stderr

    mappings = json.loads(store.read_text(encoding="utf-8"))["mappings"]
    assert len(mappings) == count
    assert {m["source"] for m in mappings} == {f"Owner/Repo{i}" for i in range(count)}


def test_older_mapping_cannot_supersede_newer_mapping(tmp_path):
    store = tmp_path / "store.json"
    newer_mapping, newer_probe = _write_inputs(tmp_path, 1, verified_at="2026-11-24T00:00:00Z")
    assert _record(tmp_path, store, newer_mapping, newer_probe).returncode == 0

    older_mapping, older_probe = _write_inputs(tmp_path, 1, verified_at="2026-11-23T00:00:00Z")
    result = _record(tmp_path, store, older_mapping, older_probe)
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert "older" in payload["error"].lower() or "supersede" in payload["error"].lower()

    mappings = json.loads(store.read_text(encoding="utf-8"))["mappings"]
    assert len(mappings) == 1
    assert mappings[0]["verified_at"] == "2026-11-24T00:00:00Z"
