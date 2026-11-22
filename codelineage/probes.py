"""Verification probes for repository mappings."""
from __future__ import annotations

import subprocess
from typing import Any


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True)


def repo_exists(repo: str) -> bool:
    cp = _run(["gh", "repo", "view", repo, "--json", "name"])
    return cp.returncode == 0


def verify_mapping(mapping: dict[str, Any]) -> dict[str, Any]:
    source = mapping.get("source")
    repo = mapping.get("repo")
    results = {"source": source, "repo": repo, "checks": {}}
    if isinstance(repo, str):
        results["checks"]["repo_exists"] = repo_exists(repo)
    else:
        results["checks"]["repo_exists"] = False
    results["ok"] = all(results["checks"].values()) if results["checks"] else False
    return results
