"""Repository mapping records."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
from .contracts import validate

def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")

def build_repository_mapping(*, source: str, destination: str, sha: str, license: str, status: str, verified_at: str | None = None) -> dict[str, Any]:
    doc = {
        "schema_version": 1,
        "source": source,
        "destination": destination,
        "sha": sha,
        "license": license,
        "status": status,
        "verified_at": verified_at or now_iso(),
    }
    validate("repository-mapping", doc)
    return doc

def mapping_from_migration_report(report: dict[str, Any]) -> dict[str, Any]:
    return build_repository_mapping(
        source=report["source"],
        destination=report["destination"],
        sha=report["sha"],
        license=report.get("license") or "NOASSERTION",
        status=report["status"],
        verified_at=report.get("generated_at"),
    )
