# Copyright (c) 2026, René Moser <mail@renemoser.net>
# SPDX-License-Identifier: Apache-2.0

"""Tests for the CloudStack type mapping and shape deduplication."""

from typing import Any

import pytest

from cloudstack_openapi.schemas import (
    DATE_NOTE,
    LIST_NOTE,
    SchemaRegistry,
    clean_fields,
    described,
    join_description,
)


@pytest.fixture
def registry() -> SchemaRegistry:
    return SchemaRegistry()


def test_clean_fields_drops_padding() -> None:
    assert clean_fields([{"name": "id"}, {}, {"name": "x"}]) == [{"name": "id"}, {"name": "x"}]
    assert clean_fields(None) == []


@pytest.mark.parametrize(
    ("base", "expected"),
    [
        ("Lists zones", "Lists zones. NOTE"),
        ("Lists zones.", "Lists zones. NOTE"),
        ("Really?", "Really? NOTE"),
        ("", "NOTE"),
        (None, "NOTE"),
    ],
)
def test_join_description(base: str | None, expected: str) -> None:
    assert join_description(base, "NOTE") == expected


def test_described_skips_empty_descriptions() -> None:
    assert described({"type": "string"}, "") == {"type": "string"}
    assert described({"type": "string"}, "hi") == {"type": "string", "description": "hi"}


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ({"name": "id", "type": "uuid"}, {"type": "string", "format": "uuid"}),
        ({"name": "n", "type": "long"}, {"type": "integer", "format": "int64"}),
        ({"name": "n", "type": "integer"}, {"type": "integer", "format": "int32"}),
        ({"name": "ok", "type": "boolean"}, {"type": "boolean"}),
        ({"name": "ratio", "type": "double"}, {"type": "number", "format": "double"}),
        ({"name": "n", "type": "short[]"}, {"type": "array", "items": {"type": "integer", "format": "int32"}}),
        # A field without a type defaults to string.
        ({"name": "x"}, {"type": "string"}),
    ],
)
def test_map_type_scalars(registry: SchemaRegistry, field: dict[str, Any], expected: dict[str, Any]) -> None:
    assert registry.map_type(field, response=True) == expected


def test_map_type_dates_stay_strings_with_a_note(registry: SchemaRegistry) -> None:
    schema = registry.map_type({"name": "created", "type": "date"}, response=True)
    # Not "format: date-time": CloudStack renders a numeric offset without a colon.
    assert schema["type"] == "string"
    assert "format" not in schema
    assert schema["x-cloudstack-type"] == "date"
    assert schema["description"] == DATE_NOTE


def test_map_type_enum_like_types_keep_their_name(registry: SchemaRegistry) -> None:
    schema = registry.map_type({"name": "state", "type": "powerstate"}, response=True)
    assert schema == {"type": "string", "x-cloudstack-type": "powerstate"}


def test_map_type_nested_response_types_are_opaque_objects(registry: SchemaRegistry) -> None:
    schema = registry.map_type({"name": "job", "type": "asyncjobresponse"}, response=True)
    assert schema == {"type": "object", "x-cloudstack-type": "asyncjobresponse"}


def test_map_type_request_list_is_comma_joined_strings(registry: SchemaRegistry) -> None:
    schema = registry.map_type({"name": "ids", "type": "list"}, response=False)
    assert schema["items"] == {"type": "string"}
    assert schema["description"] == LIST_NOTE


def test_map_type_response_list_without_a_shape_is_unconstrained(registry: SchemaRegistry) -> None:
    schema = registry.map_type({"name": "downloaddetails", "type": "set"}, response=True)
    assert schema == {"type": "array", "items": {}, "x-cloudstack-type": "set"}


def test_map_type_request_map_is_indexed(registry: SchemaRegistry) -> None:
    schema = registry.map_type({"name": "tags", "type": "map"}, response=False)
    assert schema["additionalProperties"] == {"type": "string"}
    assert schema["x-cloudstack-encoding"] == "indexed-map"
    assert "tags[0].key=k" in schema["description"]


def test_map_type_response_map_carries_arbitrary_values(registry: SchemaRegistry) -> None:
    schema = registry.map_type({"name": "details", "type": "map"}, response=True)
    assert schema["additionalProperties"] == {}
    assert "x-cloudstack-encoding" not in schema


def test_signature_ignores_field_order_and_descriptions() -> None:
    a = [{"name": "b", "type": "string", "description": "one"}, {"name": "a", "type": "uuid"}]
    b = [{"name": "a", "type": "uuid", "description": "other"}, {"name": "b", "type": "string"}]
    assert SchemaRegistry.signature(a) == SchemaRegistry.signature(b)


def test_signature_distinguishes_nested_shapes() -> None:
    a = [{"name": "n", "type": "list", "response": [{"name": "x", "type": "string"}]}]
    b = [{"name": "n", "type": "list", "response": [{"name": "y", "type": "string"}]}]
    assert SchemaRegistry.signature(a) != SchemaRegistry.signature(b)


def test_identical_shapes_collapse_into_one_schema(registry: SchemaRegistry) -> None:
    fields = [{"name": "id", "type": "uuid"}, {"name": "name", "type": "string"}]
    first = registry.add(fields, "listZones", "top")
    second = registry.add(list(reversed(fields)), "updateZone", "top")

    assert first == second
    registry.finalize()
    assert registry.ref(first) == registry.ref(second) == {"$ref": "#/components/schemas/Zone"}


def test_nested_shapes_are_named_after_the_field_carrying_them(registry: SchemaRegistry) -> None:
    fields = [{"name": "nic", "type": "list", "response": [{"name": "ipaddress", "type": "string"}]}]
    registry.add(fields, "listVirtualMachines", "top")
    schemas = registry.finalize()
    assert "Nic" in schemas


def test_delete_style_shape_is_named_success_result(registry: SchemaRegistry) -> None:
    registry.add([{"name": "success", "type": "boolean"}, {"name": "displaytext", "type": "string"}], "deleteZone", "top")
    assert "SuccessResult" in registry.finalize()


def test_shape_shared_by_disagreeing_commands_is_named_after_one_command(registry: SchemaRegistry) -> None:
    fields = [{"name": "value", "type": "string"}]
    registry.add(fields, "listZones", "top")
    registry.add(fields, "listAlerts", "top")
    assert "ListAlertsResult" in registry.finalize()


def test_colliding_names_are_suffixed(registry: SchemaRegistry) -> None:
    registry.add([{"name": "a", "type": "string"}], "listZones", "top")
    registry.add([{"name": "b", "type": "string"}], "updateZone", "top")
    assert set(registry.finalize()) == {"Zone", "Zone2"}


def test_built_schema_sorts_its_properties(registry: SchemaRegistry) -> None:
    signature = registry.add(
        [{"name": "name", "type": "string"}, {"name": "created", "type": "date"}, {"name": "id", "type": "uuid"}],
        "listZones",
        "top",
    )
    schemas = registry.finalize()
    name = registry.ref(signature)["$ref"].rsplit("/", 1)[-1]
    assert list(schemas[name]["properties"]) == ["created", "id", "name"]


def test_three_way_name_collision_keeps_counting(registry: SchemaRegistry) -> None:
    for index, command in enumerate(["listZones", "updateZone", "deleteZone"]):
        registry.add([{"name": f"f{index}", "type": "string"}], command, "top")
    assert set(registry.finalize()) == {"Zone", "Zone2", "Zone3"}


def test_nested_object_field_becomes_a_ref(registry: SchemaRegistry) -> None:
    signature = registry.add(
        [{"name": "vm", "type": "virtualmachineresponse", "response": [{"name": "id", "type": "uuid"}]}],
        "listZones",
        "top",
    )
    schemas = registry.finalize()
    name = registry.ref(signature)["$ref"].rsplit("/", 1)[-1]
    assert schemas[name]["properties"]["vm"] == {"$ref": "#/components/schemas/Vm"}


def test_nested_object_field_with_a_description_wraps_the_ref(registry: SchemaRegistry) -> None:
    field = {"name": "vm", "type": "vmresponse", "description": "the machine", "response": [{"name": "id", "type": "uuid"}]}
    registry.add([field], "listZones", "top")
    registry.finalize()

    schema = registry.map_type(field, response=True)
    assert schema == {"allOf": [{"$ref": "#/components/schemas/Vm"}], "description": "the machine"}
