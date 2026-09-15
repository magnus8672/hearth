"""Create shared valid and adversarial schema fixtures; no real identities or credentials."""
import json
from pathlib import Path

from hearth.contracts import CONTRACTS

ROOT = Path(__file__).resolve().parents[1]
bundle = json.loads((ROOT / "packages/contracts/schema/hearth.json").read_text())
definitions = bundle["$defs"]


def example(schema, name=""):
    if "$ref" in schema:
        return example(definitions[schema["$ref"].split("/")[-1]], name)
    if "const" in schema:
        return schema["const"]
    if "enum" in schema:
        return schema["enum"][0]
    if "anyOf" in schema:
        return example(next(item for item in schema["anyOf"] if item.get("type") != "null"), name)
    kind = schema.get("type")
    if kind == "object":
        if name == "settings_schema":
            return {"type": "object", "additionalProperties": False}
        return {key: example(value, key) for key, value in schema.get("properties", {}).items()
                if key in schema.get("required", []) or key == "schema_version"}
    if kind == "array":
        return [example(schema["items"]) for _ in range(schema.get("minItems", 0))]
    if kind == "string":
        if schema.get("format") == "uuid":
            return "00000000-0000-4000-8000-000000000001"
        if schema.get("format") == "date-time":
            return "2026-09-12T19:00:00Z"
        if name == "control_origin":
            return "https://127.0.0.1:8443"
        if "{64}" in schema.get("pattern", ""):
            return "a" * 64
        if "{43}" in schema.get("pattern", ""):
            return "a" * 43
        return "fixture" + "x" * max(0, schema.get("minLength", 0) - 7)
    if kind in {"integer", "number"}:
        return schema.get("minimum", 1)
    if kind == "boolean":
        return True
    return {}


cases = []
for name, model in sorted(CONTRACTS.items()):
    payload = example(definitions[name])
    if name == "GeometryRequest":
        payload["prompt"] = "A fixture stone arch"
    if name == 'ImagePromptPlan':
        payload['prompt'] = 'A fixture stone arch'
    payload = model.model_validate(payload).model_dump(mode="json")
    cases.extend([
        {"name": name + ".valid", "contract": name, "valid": True, "payload": payload},
        {"name": name + ".unknown_authority", "contract": name, "valid": False, "payload": payload | {"is_admin": True}},
        {"name": name + ".future_version", "contract": name, "valid": False, "payload": payload | {"schema_version": payload["schema_version"] + 1}},
        {"name": name + ".boolean_version", "contract": name, "valid": False, "payload": payload | {"schema_version": True}},
    ])
path = ROOT / "tests/fixtures/contracts.json"
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(cases, indent=2) + "\n")
print(f"Generated {len(cases)} shared fixtures.")
