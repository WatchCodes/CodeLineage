from __future__ import annotations
import json, os
from pathlib import Path
from typing import Any
from jsonschema import Draft202012Validator
SCHEMA_NAMES={"discovery-manifest":"discovery-manifest.schema.json","migration-request":"migration-request.schema.json","repository-mapping":"repository-mapping.schema.json","migration-report":"migration-report.schema.json","upstream-report":"upstream-report.schema.json","batch-readiness-report":"batch-readiness-report.schema.json","common":"common.definitions.json"}
def _schemas_dir():
    env=os.environ.get("WATCHCODES_SCHEMAS_DIR")
    if env: return Path(env)
    here=Path(__file__).resolve().parent
    c=here.parent.parent/"CodeFoundry"/"schemas"
    return c if c.is_dir() else here.parent/"schemas"
def load_schema(name): return json.loads((_schemas_dir()/SCHEMA_NAMES[name]).read_text(encoding="utf-8"))
def _registry():
    from referencing import Registry, Resource
    r=Registry()
    for fn in SCHEMA_NAMES.values():
        s=json.loads((_schemas_dir()/fn).read_text(encoding="utf-8"))
        res=Resource.from_contents(s)
        if s.get("$id"): r=r.with_resource(s["$id"], res)
        r=r.with_resource(fn,res)
    return r
def validate(name, document):
    Draft202012Validator(load_schema(name), registry=_registry()).validate(document)
