# Copyright (c) 2026, René Moser <mail@renemoser.net>
# SPDX-License-Identifier: Apache-2.0

"""Translation of CloudStack response objects into shared OpenAPI schemas."""

import json
from collections import Counter
from dataclasses import dataclass, field

from ._types import Json, Kind, Schema
from .naming import entity_name, pascal_case

# CloudStack scalar types -> OpenAPI schema. Anything absent here is handled by
# SchemaRegistry.map_type().
SCALAR_TYPES: dict[str, Schema] = {
    "string": {"type": "string"},
    "uuid": {"type": "string", "format": "uuid"},
    "boolean": {"type": "boolean"},
    "integer": {"type": "integer", "format": "int32"},
    "int": {"type": "integer", "format": "int32"},
    "short": {"type": "integer", "format": "int32"},
    "long": {"type": "integer", "format": "int64"},
    "float": {"type": "number", "format": "float"},
    "double": {"type": "number", "format": "double"},
    "bigdecimal": {"type": "number"},
    # CloudStack renders dates as "2026-07-29T11:18:10+0000", which is ISO 8601
    # but not RFC 3339 (no colon in the offset), so "format: date-time" would be
    # a lie. Request parameters additionally accept a bare "yyyy-MM-dd".
    "date": {"type": "string"},
    "tzdate": {"type": "string"},
    # Only ever used for opaque strings such as a MAC address or a URL.
    "object": {"type": "string"},
}

DATE_NOTE = 'CloudStack date, ISO 8601 with a numeric offset, for example "2026-07-29T11:18:10+0000".'
MAP_NOTE = "Map parameter. CloudStack expects it index-encoded as `{name}[0].key=k&{name}[0].value=v`."
LIST_NOTE = "List parameter. CloudStack expects the values comma-separated in a single occurrence."


def clean_fields(fields: list[Json] | None) -> list[Json]:
    """listApis pads response field lists with empty objects; drop them."""
    return [f for f in (fields or []) if f.get("name")]


def join_description(base: str | None, note: str) -> str:
    """Append a generator note to a listApis description without running it together."""
    base = (base or "").strip()
    if not base:
        return note
    if base[-1] not in ".!?":
        base += "."
    return f"{base} {note}"


def described(schema: Schema, description: str | None) -> Schema:
    """Attach a description to a schema when there is one."""
    if description:
        schema["description"] = description
    return schema


@dataclass
class Shape:
    """One structurally distinct CloudStack response object."""

    fields: list[Json]
    labels: list[tuple[str, Kind]] = field(default_factory=list)
    name: str = ""


class SchemaRegistry:
    """Collects response object shapes and deduplicates structurally identical ones.

    A CloudStack response object (a virtual machine, a NIC, a tag, ...) is
    repeated verbatim in every command that returns it -- 1376 objects collapse
    to roughly 250 distinct shapes -- so each shape becomes one component schema
    that the operations reference.
    """

    def __init__(self) -> None:
        self._by_signature: dict[str, Shape] = {}
        self.schemas: dict[str, Schema] = {}

    @staticmethod
    def signature(fields: list[Json] | None) -> str:
        """A stable identity for an object shape, ignoring descriptions and order."""
        parts = [
            (
                f["name"],
                f.get("type") or "",
                SchemaRegistry.signature(nested) if (nested := f.get("response")) else "",
            )
            for f in sorted(clean_fields(fields), key=lambda f: f["name"])
        ]
        return json.dumps(parts, sort_keys=True)

    def add(self, fields: list[Json] | None, label: str, kind: Kind) -> str:
        """Register an object shape. Returns its signature; names are assigned later."""
        cleaned = clean_fields(fields)
        signature = self.signature(cleaned)
        shape = self._by_signature.setdefault(signature, Shape(fields=cleaned))
        shape.labels.append((label, kind))
        for entry in cleaned:
            if nested := entry.get("response"):
                self.add(nested, entry["name"], "nested")
        return signature

    @staticmethod
    def _preferred_name(shape: Shape) -> str:
        """Name a shape after what it structurally is, not after one of its users."""
        if nested_labels := [label for label, kind in shape.labels if kind == "nested"]:
            return pascal_case(Counter(nested_labels).most_common(1)[0][0])

        names = {f["name"] for f in shape.fields}
        if names <= {"success", "displaytext", "jobid", "jobstatus"} and "success" in names:
            # Shared by every delete-style command, so no single command should name it.
            return "SuccessResult"

        # A top-level shape: if the commands returning it agree on an entity,
        # the shape is that entity (29 commands return the VirtualMachine shape).
        commands = [label for label, kind in shape.labels if kind == "top"]
        entity, hits = Counter(entity_name(command) for command in commands).most_common(1)[0]
        if hits > 1 or len(commands) == 1:
            return entity
        return f"{pascal_case(sorted(commands)[0])}Result"

    def finalize(self) -> dict[str, Schema]:
        """Assign a unique name to every shape and build the component schemas."""
        used: set[str] = set()
        for shape in self._by_signature.values():
            name = self._preferred_name(shape) or "Object"
            if name in used:
                suffix = 2
                while f"{name}{suffix}" in used:
                    suffix += 1
                name = f"{name}{suffix}"
            used.add(name)
            shape.name = name
        self.schemas = {shape.name: self._build(shape) for shape in self._by_signature.values()}
        return self.schemas

    def ref(self, signature: str) -> Schema:
        """A ``$ref`` to the component schema of a registered shape."""
        return {"$ref": f"#/components/schemas/{self._by_signature[signature].name}"}

    def _build(self, shape: Shape) -> Schema:
        return {
            "type": "object",
            "properties": {f["name"]: self.map_type(f, response=True) for f in sorted(shape.fields, key=lambda f: f["name"])},
        }

    def map_type(self, field: Json, response: bool) -> Schema:
        """Translate one CloudStack type name into an OpenAPI schema."""
        cs_type = (field.get("type") or "string").lower()
        description = (field.get("description") or "").strip()
        nested = field.get("response")

        match cs_type:
            case _ if cs_type in SCALAR_TYPES:
                schema = dict(SCALAR_TYPES[cs_type])
                if cs_type in ("date", "tzdate"):
                    description = join_description(description, DATE_NOTE)
                if cs_type not in ("string", "uuid") and schema.get("type") == "string":
                    schema["x-cloudstack-type"] = cs_type
                return described(schema, description)

            case _ if cs_type.endswith("[]"):
                item = SCALAR_TYPES.get(cs_type.removesuffix("[]"), {"type": "string"})
                return described({"type": "array", "items": dict(item)}, description)

            case "list" | "set":
                if nested:
                    items = self.ref(self.signature(nested))
                elif response:
                    # listApis documents no element shape here, and such fields do
                    # carry objects in practice (Template.downloaddetails), so the
                    # items stay unconstrained rather than guessing "string".
                    items = {}
                else:
                    # A request list is comma-joined into one query value, so its
                    # elements are always strings on the wire.
                    items = {"type": "string"}
                if not response:
                    description = join_description(description, LIST_NOTE)
                return described({"type": "array", "items": items, "x-cloudstack-type": cs_type}, description)

            case "map":
                # On the wire a request map is always strings; a response map is not.
                schema = {
                    "type": "object",
                    "additionalProperties": {} if response else {"type": "string"},
                    "x-cloudstack-type": "map",
                }
                if not response:
                    schema["x-cloudstack-encoding"] = "indexed-map"
                    description = join_description(description, MAP_NOTE.format(name=field["name"]))
                return described(schema, description)

            case _ if nested:
                ref = self.ref(self.signature(nested))
                # A $ref sibling is allowed in OpenAPI 3.1+ but keep it unambiguous.
                return {"allOf": [ref], "description": description} if description else ref

            case _ if cs_type.endswith("response") or cs_type == "responseobject":
                return described({"type": "object", "x-cloudstack-type": cs_type}, description)

            case _:
                # Enum-like CloudStack types (state, powerstate, imageformat, ...).
                # The allowed values are not part of listApis, so only the name is
                # carried.
                return described({"type": "string", "x-cloudstack-type": cs_type}, description)


__all__ = [
    "DATE_NOTE",
    "LIST_NOTE",
    "MAP_NOTE",
    "SCALAR_TYPES",
    "SchemaRegistry",
    "Shape",
    "clean_fields",
    "described",
    "join_description",
]
