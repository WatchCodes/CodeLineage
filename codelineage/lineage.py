"""Repository mapping records."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .contracts import validate

REQUIRED_REPORT_FIELDS = ("source", "destination", "sha", "status")


def now_iso() -> str:
    """Return current UTC time in ISO-8601 Z form.

    Kept for compatibility; mapping builders require explicit timestamps for
    deterministic, idempotent records.
    """
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _require_text(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _normalize_license(value: Any) -> str | None:
    if value is None:
        return "NOASSERTION"
    if not isinstance(value, str):
        raise ValueError("license must be a string or null")
    normalized = value.strip()
    if not normalized:
        return "NOASSERTION"
    return normalized


def build_repository_mapping(
    *,
    source: str,
    destination: str,
    sha: str,
    license: str | None,
    status: str,
    verified_at: str | None = None,
) -> dict[str, Any]:
    """Build a schema-valid repository mapping record.

    Fail-closed: required fields must be present, normalized, and schema-valid.
    Deterministic/idempotent: same inputs produce the same record.
    """
    if verified_at is None:
        raise ValueError("verified_at must be provided for deterministic repository mappings")

    doc = {
        "schema_version": 1,
        "source": _require_text("source", source),
        "destination": _require_text("destination", destination),
        "sha": _require_text("sha", sha).lower(),
        "license": _normalize_license(license),
        "status": _require_text("status", status),
        "verified_at": _require_text("verified_at", verified_at),
    }
    validate("repository-mapping", doc)
    return doc


def mapping_from_migration_report(report: dict[str, Any]) -> dict[str, Any]:
    """Derive a repository mapping from a migration report.

    Fail-closed when required report fields are missing or invalid.
    """
    if not isinstance(report, dict):
        raise ValueError("report must be a mapping")

    missing = [field for field in REQUIRED_REPORT_FIELDS if field not in report]
    if missing:
        raise ValueError(f"migration report missing required fields: {', '.join(missing)}")

    verified_at = report.get("verified_at", report.get("generated_at"))
    if verified_at is None:
        raise ValueError("migration report must include verified_at or generated_at")

    return build_repository_mapping(
        source=report["source"],
        destination=report["destination"],
        sha=report["sha"],
        license=report.get("license"),
        status=report["status"],
        verified_at=verified_at,
    )
