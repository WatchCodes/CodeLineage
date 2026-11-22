"""Minimal CLI for CodeLineage contract validation and mapping records."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .contracts import ContractError, validate, validate_file
from .lineage import build_repository_mapping


def _emit(payload: Any) -> None:
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


def _load_json_object(path_str: str, *, label: str) -> dict[str, Any]:
    path = Path(path_str)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ContractError(f"{label} not found: {path}") from exc
    except OSError as exc:
        raise ContractError(f"{label} cannot be read: {path}: {exc}") from exc
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ContractError(f"{label} is not valid JSON: {path}: {exc}") from exc
    if not isinstance(document, dict):
        raise ContractError(f"{label} must be a JSON object: {path}")
    return document


def _default_store() -> Path:
    return Path(".codelineage") / "mappings.json"


def _load_store(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": 1, "mappings": []}
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ContractError(f"store is not valid JSON: {path}: {exc}") from exc
    except OSError as exc:
        raise ContractError(f"store cannot be read: {path}: {exc}") from exc
    if not isinstance(document, dict):
        raise ContractError(f"store must be a JSON object: {path}")
    if document.get("schema_version") != 1:
        raise ContractError(f"store schema_version must be 1: {path}")
    mappings = document.get("mappings")
    if not isinstance(mappings, list):
        raise ContractError(f"store mappings must be a list: {path}")
    for idx, mapping in enumerate(mappings):
        if not isinstance(mapping, dict):
            raise ContractError(f"store mappings[{idx}] must be an object: {path}")
        validate("repository-mapping", mapping)
    return {"schema_version": 1, "mappings": mappings}


def _save_store(path: Path, store: dict[str, Any]) -> None:
    if store.get("schema_version") != 1 or not isinstance(store.get("mappings"), list):
        raise ContractError("store must contain schema_version=1 and mappings list")
    for mapping in store["mappings"]:
        validate("repository-mapping", mapping)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(store, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except OSError as exc:
        raise ContractError(f"store cannot be written: {path}: {exc}") from exc


def _mapping_key(mapping: dict[str, Any]) -> tuple[str, str]:
    source = mapping.get("source")
    destination = mapping.get("destination")
    if not isinstance(source, str) or not isinstance(destination, str):
        raise ContractError("mapping source and destination must be strings")
    return source, destination


def _upsert_mapping(store: dict[str, Any], mapping: dict[str, Any]) -> dict[str, Any]:
    validate("repository-mapping", mapping)
    key = _mapping_key(mapping)
    mappings = store.setdefault("mappings", [])
    replaced = False
    for idx, existing in enumerate(mappings):
        if _mapping_key(existing) == key:
            mappings[idx] = mapping
            replaced = True
            break
    if not replaced:
        mappings.append(mapping)
    mappings.sort(key=lambda m: (str(m.get("source", "")), str(m.get("destination", ""))))
    return {"action": "updated" if replaced else "created", "mapping": mapping}


def _cmd_validate(args: argparse.Namespace) -> int:
    ok, errors = validate_file(args.schema, args.file)
    payload: dict[str, Any] = {"ok": ok, "schema": args.schema, "file": args.file}
    if not ok:
        payload["errors"] = errors
    if args.json:
        _emit(payload)
    else:
        if ok:
            print("OK")
        else:
            for error in errors:
                print(error, file=sys.stderr)
    return 0 if ok else 1


def _cmd_record(args: argparse.Namespace) -> int:
    if bool(args.report) == bool(args.mapping):
        raise ContractError("exactly one of --report or --mapping is required")
    store_path = Path(args.store) if args.store else _default_store()

    if args.report:
        report = _load_json_object(args.report, label="report")
        validate("migration-report", report)
        sha = report.get("sha")
        if not isinstance(sha, str):
            receipt = report.get("receipt")
            if isinstance(receipt, dict) and isinstance(receipt.get("source_sha"), str):
                sha = receipt["source_sha"]
        if not isinstance(sha, str):
            raise ContractError("report missing sha")

        license_value = report.get("license")
        if isinstance(license_value, dict):
            license_value = license_value.get("detected")
        if not isinstance(license_value, str):
            license_value = "NOASSERTION"

        verified_at = report.get("generated_at")
        if not isinstance(verified_at, str):
            receipt = report.get("receipt")
            checkpoints = receipt.get("checkpoints") if isinstance(receipt, dict) else None
            if isinstance(checkpoints, list):
                for cp in reversed(checkpoints):
                    if isinstance(cp, dict) and isinstance(cp.get("at"), str):
                        verified_at = cp["at"]
                        break
        if not isinstance(verified_at, str):
            from datetime import datetime, timezone

            verified_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

        mapping = build_repository_mapping(
            source=report["source"],
            destination=report["destination"],
            sha=sha,
            license=license_value,
            status=report["status"],
            verified_at=verified_at,
        )
    else:
        mapping = _load_json_object(args.mapping, label="mapping")
        validate("repository-mapping", mapping)

    if mapping.get("status") != "VERIFIED":
        raise ContractError(
            f"refusing to record unverified mapping: status={mapping.get('status')!r}"
        )

    store = _load_store(store_path)
    result = _upsert_mapping(store, mapping)
    _save_store(store_path, store)
    _emit({"ok": True, "store": str(store_path), **result})
    return 0


def _cmd_lookup(args: argparse.Namespace) -> int:
    if not args.source and not args.destination:
        raise ContractError("at least one of --source or --destination is required")
    store_path = Path(args.store) if args.store else _default_store()
    store = _load_store(store_path)
    matches = []
    for mapping in store.get("mappings", []):
        if args.source and mapping.get("source") != args.source:
            continue
        if args.destination and mapping.get("destination") != args.destination:
            continue
        matches.append(mapping)
    payload = {"ok": bool(matches), "store": str(store_path), "count": len(matches), "mappings": matches}
    _emit(payload)
    return 0 if matches else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codelineage", description="CodeLineage contract utilities.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_validate = sub.add_parser("validate", help="Validate a JSON document against a contract schema.")
    p_validate.add_argument("--schema", required=True, help="Contract schema name.")
    p_validate.add_argument("--file", required=True, help="Path to JSON document.")
    p_validate.add_argument("--json", action="store_true", default=False, help="Emit JSON output.")
    p_validate.set_defaults(func=_cmd_validate)

    p_record = sub.add_parser("record", help="Record a verified repository mapping in a local store.")
    src = p_record.add_mutually_exclusive_group(required=True)
    src.add_argument("--report", help="Path to MigrationReport JSON file.")
    src.add_argument("--mapping", help="Path to RepositoryMapping JSON file.")
    p_record.add_argument("--store", default=None, help="Path to mapping store JSON file.")
    p_record.set_defaults(func=_cmd_record)

    p_lookup = sub.add_parser("lookup", help="Lookup mappings from a local store.")
    p_lookup.add_argument("--store", default=None, help="Path to mapping store JSON file.")
    p_lookup.add_argument("--source", default=None, help="Source repository to match.")
    p_lookup.add_argument("--destination", default=None, help="Destination repository to match.")
    p_lookup.set_defaults(func=_cmd_lookup)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
        raise SystemExit(code) from exc
    try:
        return int(args.func(args))
    except ContractError as exc:
        _emit({"ok": False, "error": str(exc)})
        return 1
    except json.JSONDecodeError as exc:
        _emit({"ok": False, "error": f"Invalid JSON: {exc}"})
        return 1
    except FileNotFoundError as exc:
        _emit({"ok": False, "error": f"File not found: {exc}"})
        return 1
    except Exception as exc:  # fail closed
        _emit({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
