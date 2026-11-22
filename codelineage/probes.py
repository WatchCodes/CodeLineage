"""Verification probes for repository mappings."""
from __future__ import annotations

import shutil
import subprocess
from typing import Any

PROBE_SCHEMA_VERSION = 1
PROBE_KIND = "verification-probe"


def _run(cmd: list[str], *, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True, timeout=timeout)


def _normalize_repo(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    repo = value.strip()
    return repo or None


def repo_exists(repo: str) -> bool:
    """Return True when GitHub reports the repository exists.

    Fail-closed: any lookup failure or missing gh CLI returns False.
    """
    normalized = _normalize_repo(repo)
    if normalized is None:
        return False
    if shutil.which("gh") is None:
        return False
    try:
        cp = _run(["gh", "repo", "view", normalized, "--json", "name"])
    except Exception:
        return False
    return cp.returncode == 0


def _mapping_repo(mapping: dict[str, Any]) -> str | None:
    for key in ("destination", "repo"):
        repo = _normalize_repo(mapping.get(key))
        if repo is not None:
            return repo
    return None


def verify_mapping(mapping: dict[str, Any]) -> dict[str, Any]:
    """Verify a repository mapping and return a clear, schema-shaped record.

    The probe is fail-closed: missing inputs, missing tooling, lookup errors, or
    failed checks produce ok=False with explicit errors.
    """
    if not isinstance(mapping, dict):
        raise ValueError("mapping must be a mapping")

    source = _normalize_repo(mapping.get("source"))
    destination = _mapping_repo(mapping)
    sha = _normalize_repo(mapping.get("sha"))
    errors: list[str] = []
    checks: dict[str, bool] = {}

    if source is None:
        errors.append("missing source")
    if destination is None:
        errors.append("missing destination")
    if sha is None:
        errors.append("missing sha")

    if destination is None:
        checks["destination_exists"] = False
    else:
        try:
            cp = _run(["gh", "repo", "view", destination, "--json", "name"])
            exists = cp.returncode == 0
            checks["destination_exists"] = exists
            if not exists:
                detail = (cp.stderr or cp.stdout or "").strip()
                detail = detail[:300]
                errors.append(
                    f"destination repository not verified: {destination}"
                    + (f" ({detail})" if detail else "")
                )
        except FileNotFoundError:
            checks["destination_exists"] = False
            errors.append("gh CLI unavailable")
        except subprocess.TimeoutExpired:
            checks["destination_exists"] = False
            errors.append(f"destination repository check timed out: {destination}")
        except Exception as exc:
            checks["destination_exists"] = False
            errors.append(f"destination repository check failed: {exc.__class__.__name__}")

    # Backward-compatible alias; destination_exists is the canonical check.
    checks["repo_exists"] = checks.get("destination_exists", False)

    fatal_errors = [e for e in errors if not e.startswith("missing source") and not e.startswith("missing sha")]
    record = {
        "schema_version": PROBE_SCHEMA_VERSION,
        "kind": PROBE_KIND,
        "mapping": {
            "source": source,
            "destination": destination,
            "sha": sha.lower() if isinstance(sha, str) else None,
        },
        "checks": checks,
        "errors": errors,
        "ok": all(checks.values()) and not fatal_errors and bool(checks),
        # Backward-compatible top-level fields.
        "source": source,
        "repo": destination,
        "destination": destination,
    }
    return record
