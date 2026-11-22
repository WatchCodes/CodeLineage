"""Schema loading and validation for CodeLineage contracts.

Validation is fail-closed: unknown schemas, missing schema files, invalid JSON,
and schema violations raise errors instead of being ignored.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

SCHEMA_NAMES: dict[str, str] = {
    "discovery-manifest": "discovery-manifest.schema.json",
    "migration-request": "migration-request.schema.json",
    "repository-mapping": "repository-mapping.schema.json",
    "migration-report": "migration-report.schema.json",
    "upstream-report": "upstream-report.schema.json",
    "batch-readiness-report": "batch-readiness-report.schema.json",
    "common": "common.definitions.json",
}

CONTRACT_NAMES: tuple[str, ...] = tuple(name for name in SCHEMA_NAMES if name != "common")


class ContractError(ValueError):
    """Raised when contract validation fails or a contract cannot be loaded."""


def known_schema_names() -> tuple[str, ...]:
    return CONTRACT_NAMES


@lru_cache(maxsize=1)
def schemas_dir() -> Path:
    env = os.environ.get("WATCHCODES_SCHEMAS_DIR")
    if env:
        path = Path(env).expanduser()
        if not path.is_dir():
            raise ContractError(f"schemas directory not found: {path}")
        return path
    here = Path(__file__).resolve().parent
    candidates = [
        here.parent.parent / "CodeFoundry" / "schemas",
        here.parent / "schemas",
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    raise ContractError(
        "schemas directory not found; set WATCHCODES_SCHEMAS_DIR or install CodeFoundry schemas"
    )


def _schema_path(name: str) -> Path:
    if name not in SCHEMA_NAMES:
        raise ContractError(
            f"unknown schema: {name!r}; known: {', '.join(sorted(SCHEMA_NAMES))}"
        )
    path = schemas_dir() / SCHEMA_NAMES[name]
    if not path.is_file():
        raise ContractError(f"schema file missing: {path}")
    return path


@lru_cache(maxsize=None)
def load_schema(name: str) -> dict[str, Any]:
    path = _schema_path(name)
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ContractError(f"invalid JSON in schema {name!r} ({path}): {exc}") from exc
    if not isinstance(schema, dict):
        raise ContractError(f"schema {name!r} must be a JSON object: {path}")
    return schema


@lru_cache(maxsize=1)
def _registry():
    from referencing import Registry, Resource

    registry = Registry()
    for filename in SCHEMA_NAMES.values():
        path = schemas_dir() / filename
        try:
            schema = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ContractError(f"invalid JSON in schema file {path}: {exc}") from exc
        if not isinstance(schema, dict):
            raise ContractError(f"schema file must be a JSON object: {path}")
        resource = Resource.from_contents(schema)
        schema_id = schema.get("$id")
        if isinstance(schema_id, str) and schema_id:
            registry = registry.with_resource(schema_id, resource)
        registry = registry.with_resource(filename, resource)
    return registry


@lru_cache(maxsize=None)
def validator_for(name: str) -> Draft202012Validator:
    return Draft202012Validator(load_schema(name), registry=_registry())


def _format_error_path(error: ValidationError) -> str:
    location = "$"
    for part in error.path:
        if isinstance(part, int):
            location += f"[{part}]"
        else:
            location += f".{part}"
    return location


def format_errors(name: str, errors: list[ValidationError]) -> list[str]:
    ordered = sorted(errors, key=lambda err: (list(err.path), err.message))
    formatted: list[str] = []
    for err in ordered:
        formatted.append(f"{name}{_format_error_path(err)}: {err.message}")
    return formatted


def validate(name: str, document: Any) -> None:
    errors = sorted(validator_for(name).iter_errors(document), key=lambda e: (list(e.path), e.message))
    if not errors:
        return
    messages = format_errors(name, errors)
    details = "\n".join(messages)
    raise ContractError(
        f"{name} schema validation failed ({len(messages)} error{'s' if len(messages) != 1 else ''}):\n{details}"
    )


def is_valid(name: str, document: Any) -> tuple[bool, list[str]]:
    try:
        errors = sorted(validator_for(name).iter_errors(document), key=lambda e: (list(e.path), e.message))
    except Exception as exc:  # fail closed
        return False, [f"{name}$: {type(exc).__name__}: {exc}"]
    if not errors:
        return True, []
    return False, format_errors(name, errors)


def validate_file(name: str, file_path: str | os.PathLike[str]) -> tuple[bool, list[str]]:
    path = Path(file_path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return False, [f"{name}$: file not found: {path}"]
    except OSError as exc:
        return False, [f"{name}$: cannot read file {path}: {exc}"]
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        return False, [f"{name}$: invalid JSON in {path}: {exc}"]
    return is_valid(name, document)
