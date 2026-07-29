"""Generate Dart data classes from the running service's OpenAPI schema.

The plan called for a generated Dart client so it cannot drift from the backend.
Rather than pull in openapi-generator — which emits tens of thousands of lines
of Dio-flavoured code for a schema this size — this walks
`components.schemas` and writes exactly the immutable data classes the app
needs. The output is small enough to read in review, which matters: a generator
nobody reads is a place bugs go to hide.

Usage:
    python scripts/generate_dart_models.py [--url http://localhost:8000/openapi.json]
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.request
from pathlib import Path
from typing import Any

OUTPUT = Path(__file__).resolve().parent.parent / "mobile" / "lib" / "api" / "models.dart"

HEADER = """// GENERATED — do not edit by hand.
//
// Regenerate with:  python scripts/generate_dart_models.py
// Source: the service's own OpenAPI schema, so these cannot drift from the API.

// ignore_for_file: unnecessary_this, prefer_if_null_operators

/// Parses the API's ISO-8601 timestamps, which are always UTC on the wire.
DateTime? _date(Object? value) =>
    value == null ? null : DateTime.parse(value as String).toUtc();

double? _double(Object? value) => value == null ? null : (value as num).toDouble();

int? _int(Object? value) => value == null ? null : (value as num).toInt();
"""

# Schemas the app never touches; generating them is noise.
SKIP = re.compile(r"^(HTTPValidationError|ValidationError|Body_)")


def dart_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", name)


def field_name(name: str) -> str:
    parts = name.split("_")
    return parts[0] + "".join(p.title() for p in parts[1:])


def resolve(schema: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    """Follow a $ref, and collapse the anyOf[X, null] pydantic emits for optionals."""
    if "$ref" in schema:
        ref = schema["$ref"].rsplit("/", 1)[-1]
        return {"__ref__": ref}
    if "anyOf" in schema:
        variants = [v for v in schema["anyOf"] if v.get("type") != "null"]
        if len(variants) == 1:
            return resolve(variants[0], spec)
        return {"type": "object"}
    if "allOf" in schema and len(schema["allOf"]) == 1:
        return resolve(schema["allOf"][0], spec)
    return schema


# Placeholder for the JSON accessor inside a parse expression. A literal "v"
# would be substituted inside any identifier that happens to contain one.
VALUE = "__VALUE__"


def dart_type(schema: dict[str, Any], spec: dict[str, Any]) -> tuple[str, str]:
    """Return (dart type, expression parsing the value at `VALUE`)."""
    resolved = resolve(schema, spec)

    if "__ref__" in resolved:
        target = spec["components"]["schemas"][resolved["__ref__"]]
        if "enum" in target:
            return "String", f"{VALUE} as String?"
        name = dart_name(resolved["__ref__"])
        return name, f"{VALUE} == null ? null : {name}.fromJson({VALUE} as Map<String, dynamic>)"

    if "enum" in resolved:
        return "String", f"{VALUE} as String?"

    kind = resolved.get("type")
    if kind == "string":
        if resolved.get("format") in ("date-time", "date"):
            return "DateTime", f"_date({VALUE})"
        return "String", f"{VALUE} as String?"
    if kind == "integer":
        return "int", f"_int({VALUE})"
    if kind == "number":
        return "double", f"_double({VALUE})"
    if kind == "boolean":
        return "bool", f"{VALUE} as bool?"
    if kind == "array":
        inner_type, inner_parse = dart_type(resolved.get("items", {}), spec)
        element = inner_parse.replace(VALUE, "e")
        return (
            f"List<{inner_type}>",
            f"{VALUE} == null ? null : ({VALUE} as List)"
            f".map((e) => ({element})!).toList().cast<{inner_type}>()",
        )
    if kind == "object" or "additionalProperties" in resolved:
        return (
            "Map<String, dynamic>",
            f"{VALUE} == null ? null : Map<String, dynamic>.from({VALUE} as Map)",
        )
    return "dynamic", VALUE


def generate_class(name: str, schema: dict[str, Any], spec: dict[str, Any]) -> str:
    properties: dict[str, Any] = schema.get("properties", {})
    required = set(schema.get("required", []))
    cls = dart_name(name)

    fields, ctor, parse = [], [], []
    for prop, prop_schema in properties.items():
        type_name, parse_expr = dart_type(prop_schema, spec)
        member = field_name(prop)
        is_required = prop in required and prop_schema.get("default") is None

        # A nullable field on a required response is still nullable in Dart:
        # trusting the schema's `required` for non-null would crash the app the
        # first time the API legitimately returns null.
        nullable = not is_required or _is_nullable(prop_schema)
        suffix = "?" if nullable else ""
        fields.append(f"  final {type_name}{suffix} {member};")
        ctor.append(f"    {'required ' if not nullable else ''}this.{member},")

        expr = parse_expr.replace(VALUE, f"json['{prop}']")
        if not nullable:
            expr = f"({expr})!"
        parse.append(f"      {member}: {expr},")

    doc = schema.get("description", "").split("\n")[0]
    lines = [f"/// {doc}" if doc else f"/// `{name}` from the API schema."]
    lines.append(f"class {cls} {{")
    lines.extend(fields)
    lines.append("")
    lines.append(f"  const {cls}({{")
    lines.extend(ctor)
    lines.append("  });")
    lines.append("")
    lines.append(f"  factory {cls}.fromJson(Map<String, dynamic> json) => {cls}(")
    lines.extend(parse)
    lines.append("      );")
    lines.append("}")
    return "\n".join(lines)


def _is_nullable(schema: dict[str, Any]) -> bool:
    if "anyOf" in schema:
        return any(v.get("type") == "null" for v in schema["anyOf"])
    return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8000/openapi.json")
    args = parser.parse_args()

    with urllib.request.urlopen(args.url, timeout=30) as response:
        spec = json.load(response)

    schemas = spec.get("components", {}).get("schemas", {})
    chunks = [HEADER]
    generated = 0
    for name, schema in sorted(schemas.items()):
        if SKIP.match(name) or "enum" in schema or schema.get("type") != "object":
            continue
        chunks.append(generate_class(name, schema, spec))
        generated += 1

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\n\n".join(chunks) + "\n", encoding="utf-8")
    print(f"wrote {generated} classes to {OUTPUT.relative_to(OUTPUT.parent.parent.parent)}")


if __name__ == "__main__":
    main()
