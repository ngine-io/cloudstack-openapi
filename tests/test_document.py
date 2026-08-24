# Copyright (c) 2026, René Moser <mail@renemoser.net>
# SPDX-License-Identifier: Apache-2.0

"""Tests for the assembled OpenAPI document."""

import logging
from typing import Any

import pytest

from cloudstack_openapi import GeneratorOptions, build_document
from cloudstack_openapi.document import (
    OPENAPI_VERSION,
    build_parameter,
    build_payload_schema,
    dedupe_params,
)
from cloudstack_openapi.schemas import SchemaRegistry


def parameters_of(document: dict[str, Any], command: str) -> dict[str, Any]:
    """The named query parameters of an operation, keyed by name."""
    params = document["paths"][f"/{command}"]["get"]["parameters"]
    return {p["name"]: p for p in params if "name" in p}


def payload_of(document: dict[str, Any], command: str) -> Any:
    """The schema of the body inside the response envelope."""
    schema = document["paths"][f"/{command}"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    return schema["properties"][f"{command.lower()}response"]


def test_document_skeleton(document: dict[str, Any]) -> None:
    assert document["openapi"] == OPENAPI_VERSION
    assert document["info"]["license"]["identifier"] == "Apache-2.0"
    assert document["security"] == [{"apiKey": [], "signature": []}, {"sessionKey": []}]
    assert set(document["components"]["securitySchemes"]) == {"apiKey", "signature", "sessionKey"}
    assert "$self" not in document


def test_options_are_reflected(apis: list[dict[str, Any]]) -> None:
    options = GeneratorOptions(
        server_url="https://cloud.example.com/client/api",
        title="Example Cloud",
        api_version="4.22.0.0",
        self_uri="https://example.com/openapi.yaml",
    )
    document = build_document(apis, options)

    assert document["$self"] == "https://example.com/openapi.yaml"
    assert document["info"]["title"] == "Example Cloud"
    assert document["info"]["version"] == "4.22.0.0"
    assert document["servers"][0]["url"] == "https://cloud.example.com/client/api"


def test_one_synthetic_path_per_command(document: dict[str, Any], apis: list[dict[str, Any]]) -> None:
    assert set(document["paths"]) == {f"/{api['name']}" for api in apis}
    for path, item in document["paths"].items():
        assert list(item) == ["get"]
        assert item["get"]["operationId"] == path.removeprefix("/")


def test_command_parameter_is_pinned_first(document: dict[str, Any]) -> None:
    first = document["paths"]["/listZones"]["get"]["parameters"][0]
    assert first["name"] == "command"
    assert first["required"] is True
    # "default" repeats "const" so browsers prefill the required parameter.
    assert first["schema"]["const"] == first["schema"]["default"] == "listZones"


def test_common_response_parameter_is_referenced(document: dict[str, Any]) -> None:
    assert {"$ref": "#/components/parameters/response"} in document["paths"]["/listZones"]["get"]["parameters"]


def test_paths_and_schemas_are_sorted(document: dict[str, Any]) -> None:
    assert list(document["paths"]) == sorted(document["paths"])
    schemas = list(document["components"]["schemas"])
    # The two generator-owned schemas come first, the rest is sorted.
    assert schemas[:2] == ["CloudStackError", "AsyncJobStart"]
    assert schemas[2:] == sorted(schemas[2:])


def test_build_document_is_deterministic(apis: list[dict[str, Any]]) -> None:
    assert build_document(apis) == build_document(list(reversed(apis)))


def test_required_parameters_come_first(document: dict[str, Any]) -> None:
    names = [p["name"] for p in document["paths"]["/deployVirtualMachine"]["get"]["parameters"] if "name" in p]
    assert names == ["command", "serviceofferingid", "displayname"]


def test_string_length_becomes_max_length(document: dict[str, Any]) -> None:
    assert parameters_of(document, "listZones")["name"]["schema"]["maxLength"] == 255


def test_list_parameters_are_comma_separated(document: dict[str, Any]) -> None:
    ids = parameters_of(document, "listZones")["ids"]
    assert (ids["style"], ids["explode"]) == ("form", False)


def test_map_parameters_carry_the_indexed_encoding(document: dict[str, Any]) -> None:
    tags = parameters_of(document, "listZones")["tags"]
    assert tags["x-cloudstack-encoding"] == "indexed-map"
    # The encoding annotation belongs on the parameter, not on its schema.
    assert "x-cloudstack-encoding" not in tags["schema"]


def test_extensions_are_carried_over(document: dict[str, Any]) -> None:
    operation = document["paths"]["/listZones"]["get"]
    assert operation["x-cloudstack-since"] == "3.0.0"
    assert operation["x-cloudstack-related"] == ["createZone", "updateZone"]
    assert parameters_of(document, "listZones")["ids"]["x-cloudstack-related"] == ["listZones"]


def test_duplicate_parameters_are_merged_keeping_required() -> None:
    api = {
        "name": "listZones",
        "params": [
            {"name": "id", "type": "uuid", "description": "first"},
            {"name": "id", "type": "uuid", "description": "second", "required": True},
        ],
    }
    (param,) = dedupe_params(api)
    assert param["description"] == "first"
    assert param["required"] is True


def test_reserved_parameters_are_dropped_with_a_warning(caplog: pytest.LogCaptureFixture) -> None:
    api = {"name": "listZones", "params": [{"name": "response", "type": "string"}]}
    with caplog.at_level(logging.WARNING, logger="cloudstack_openapi.document"):
        assert dedupe_params(api) == []
    assert "reserved parameter" in caplog.text


def test_build_parameter_marks_optional_parameters_by_omission() -> None:
    parameter = build_parameter({"name": "id", "type": "uuid"}, SchemaRegistry())
    assert "required" not in parameter


def test_sync_list_command_payload_allows_the_counted_envelope(document: dict[str, Any]) -> None:
    payload = payload_of(document, "listZones")
    assert payload["properties"]["count"]["type"] == "integer"
    # The payload key is unknown without probing, so any key is accepted.
    assert "oneOf" in payload["additionalProperties"]


def test_sync_non_list_command_payload_allows_both_renderings(document: dict[str, Any]) -> None:
    payload = payload_of(document, "updateZone")
    assert len(payload["oneOf"]) == 2
    assert payload["oneOf"][0] == {"$ref": "#/components/schemas/Zone"}


def test_probed_response_key_pins_the_payload(apis: list[dict[str, Any]]) -> None:
    options = GeneratorOptions(response_keys={"listZones": ("zone", True)})
    payload = payload_of(build_document(apis, options), "listZones")

    assert payload["properties"]["zone"] == {"type": "array", "items": {"$ref": "#/components/schemas/Zone"}}
    assert payload["properties"]["count"]["type"] == "integer"


def test_probed_singular_response_key_is_not_an_array(apis: list[dict[str, Any]]) -> None:
    options = GeneratorOptions(response_keys={"updateZone": ("zone", False)})
    payload = payload_of(build_document(apis, options), "updateZone")

    assert payload["properties"] == {"zone": {"$ref": "#/components/schemas/Zone"}}


def test_build_payload_schema_without_a_registered_entity() -> None:
    registry = SchemaRegistry()
    signature = registry.add([{"name": "id", "type": "uuid"}], "listZones", "top")
    registry.finalize()

    payload = build_payload_schema({"name": "listZones"}, signature, registry, None)
    assert payload["type"] == "object"


def test_async_command_returns_a_job_acknowledgement(document: dict[str, Any]) -> None:
    operation = document["paths"]["/deployVirtualMachine"]["get"]
    assert payload_of(document, "deployVirtualMachine") == {"$ref": "#/components/schemas/AsyncJobStart"}
    assert operation["x-cloudstack-async"] is True
    # The documented entity arrives later, via queryAsyncJobResult.
    assert operation["x-cloudstack-jobresult-schema"] == "#/components/schemas/VirtualMachine"
    assert "queryAsyncJobResult" in operation["description"]


def test_sync_command_is_marked_as_such(document: dict[str, Any]) -> None:
    assert document["paths"]["/listZones"]["get"]["x-cloudstack-async"] is False


def test_error_response_reuses_the_envelope_key(document: dict[str, Any]) -> None:
    default = document["paths"]["/listZones"]["get"]["responses"]["default"]
    schema = default["content"]["application/json"]["schema"]
    assert schema["required"] == ["listzonesresponse"]
    assert schema["properties"]["listzonesresponse"] == {"$ref": "#/components/schemas/CloudStackError"}


def test_summary_is_the_first_sentence_only(document: dict[str, Any]) -> None:
    operation = document["paths"]["/listZones"]["get"]
    assert operation["summary"] == "Lists zones."
    assert operation["description"].startswith("Lists zones. Only zones")


def test_description_is_omitted_when_it_repeats_the_summary(document: dict[str, Any]) -> None:
    assert "description" not in document["paths"]["/updateZone"]["get"]


def test_shared_shapes_are_emitted_once(document: dict[str, Any]) -> None:
    schemas = document["components"]["schemas"]
    assert schemas["VirtualMachine"]["properties"]["nic"]["items"] == {"$ref": "#/components/schemas/Nic"}
    assert schemas["Zone"]["properties"]["tags"]["items"] == {"$ref": "#/components/schemas/Tags"}
    # deleteZone's {success, displaytext} shape is named after what it is.
    assert "SuccessResult" in schemas


def test_padding_objects_are_dropped_from_shapes(document: dict[str, Any]) -> None:
    assert "" not in document["components"]["schemas"]["Zone"]["properties"]


def test_tags_group_commands_by_entity(document: dict[str, Any]) -> None:
    tags = {tag["name"]: tag["description"] for tag in document["tags"]}
    assert set(tags) == {"Zone", "VirtualMachine"}
    # addNicToVirtualMachine joins VirtualMachine rather than forming its own group.
    assert document["paths"]["/addNicToVirtualMachine"]["get"]["tags"] == ["VirtualMachine"]
    assert tags["Zone"] == "3 commands acting on Zone."


def test_tag_description_is_singular_for_one_command() -> None:
    apis = [
        {"name": "login", "description": "Logs in.", "isasync": False, "response": [{"name": "sessionkey", "type": "string"}]}
    ]
    (tag,) = build_document(apis)["tags"]
    assert tag["description"] == "1 command acting on Login."


def test_parameter_since_is_carried_over() -> None:
    parameter = build_parameter({"name": "id", "type": "uuid", "since": "4.4.0"}, SchemaRegistry())
    assert parameter["x-cloudstack-since"] == "4.4.0"
