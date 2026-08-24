# Copyright (c) 2026, René Moser <mail@renemoser.net>
# SPDX-License-Identifier: Apache-2.0

"""Assembly of the OpenAPI document from a ``listApis`` catalogue."""

import logging
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field

from ._types import Json, Schema
from .naming import build_tagger, envelope_key, first_sentence, related_commands
from .schemas import SchemaRegistry

logger = logging.getLogger(__name__)

OPENAPI_VERSION = "3.2.0"

DEFAULT_SERVER_URL = "https://localhost:8443/client/api"
DEFAULT_TITLE = "Apache CloudStack API"

# Injected by this generator, so a command may not redefine them.
RESERVED_PARAMETERS = ("command", "response", "apiKey", "signature", "sessionkey")

COMMON_PARAMETERS: dict[str, Json] = {
    "response": {
        "name": "response",
        "in": "query",
        "description": "Format of the response body. This document only describes the JSON rendering.",
        "required": False,
        "schema": {"type": "string", "enum": ["json", "xml"], "default": "json"},
    },
    "page": {
        "name": "page",
        "in": "query",
        "description": "Page to return, used together with `pagesize`.",
        "required": False,
        "schema": {"type": "integer", "format": "int32", "minimum": 1},
    },
}

SECURITY_SCHEMES: dict[str, Json] = {
    "apiKey": {
        "type": "apiKey",
        "in": "query",
        "name": "apiKey",
        "description": "API key of the CloudStack user. Must be sent together with `signature`.",
    },
    "signature": {
        "type": "apiKey",
        "in": "query",
        "name": "signature",
        "description": (
            "Base64-encoded HMAC-SHA1 of the lower-cased, alphabetically sorted, "
            "URL-encoded query string, signed with the user's secret key."
        ),
    },
    "sessionKey": {
        "type": "apiKey",
        "in": "query",
        "name": "sessionkey",
        "description": "Session key obtained from `login`, used instead of `apiKey` plus `signature`.",
    },
}

ERROR_SCHEMA: Schema = {
    "type": "object",
    "description": "Error body CloudStack returns in place of the documented payload.",
    "properties": {
        "errorcode": {"type": "integer", "description": "Error code, mirrored in the HTTP status."},
        "cserrorcode": {"type": "integer", "description": "CloudStack specific error code."},
        "errortext": {"type": "string", "description": "Human readable error message."},
        "uuidList": {
            "type": "array",
            "description": "UUIDs of the entities the error refers to.",
            "items": {"type": "object"},
        },
    },
}

ASYNC_SCHEMA: Schema = {
    "type": "object",
    "description": (
        "Acknowledgement of an asynchronous command. Poll `queryAsyncJobResult` with `jobid` to obtain the documented payload."
    ),
    "properties": {
        "jobid": {"type": "string", "format": "uuid", "description": "ID of the async job."},
        "id": {"type": "string", "description": "ID of the entity the job acts on, when already known."},
    },
    "additionalProperties": True,
}

DESCRIPTION_HEADER = """\
OpenAPI rendering of the Apache CloudStack API, generated from the `listApis`
command.

**Paths in this document are synthetic.** CloudStack exposes a single endpoint
and selects the command with a query parameter, which OpenAPI cannot express:
every request actually goes to `{server}?command=<operationId>`. Each operation
is therefore keyed by a path named after its command, and carries a required
`command` parameter pinned to that command. A client generated from this
document must send the `command` parameter and ignore the path segment.

Every response body is wrapped by CloudStack in a single `<command>response`
key, which is reflected in the schemas. `listApis` describes the *entity* a
command returns rather than that envelope, so for non-list commands the payload
is modelled as either the entity itself or the entity nested under a
command-specific key.

Requests are authenticated with `apiKey` plus a `signature` computed from the
request, or with a `sessionkey` obtained from `login`.\
"""


@dataclass
class GeneratorOptions:
    """Everything that influences the document but does not come from ``listApis``."""

    server_url: str = DEFAULT_SERVER_URL
    title: str = DEFAULT_TITLE
    api_version: str = "unknown"
    self_uri: str | None = None
    #: Command -> (payload key, whether the payload is an array), as resolved by
    #: :func:`cloudstack_openapi.source.probe_response_keys`.
    response_keys: dict[str, tuple[str, bool]] = field(default_factory=dict)


def build_parameter(param: Json, registry: SchemaRegistry) -> Json:
    """Translate one ``listApis`` request parameter into an OpenAPI query parameter."""
    schema = registry.map_type(param, response=False)
    description = schema.pop("description", None)
    encoding = schema.pop("x-cloudstack-encoding", None)

    parameter: Json = {"name": param["name"], "in": "query"}
    if description:
        parameter["description"] = description
    if param.get("required"):
        parameter["required"] = True
    if (param.get("type") or "string").lower() in ("list", "set"):
        # ids=a,b,c rather than ids=a&ids=b&ids=c
        parameter["style"] = "form"
        parameter["explode"] = False
    if encoding:
        parameter["x-cloudstack-encoding"] = encoding
    if (length := param.get("length")) and schema.get("type") == "string":
        schema["maxLength"] = length
    parameter["schema"] = schema
    if since := param.get("since"):
        parameter["x-cloudstack-since"] = since
    if related := related_commands(param.get("related")):
        parameter["x-cloudstack-related"] = related
    return parameter


def dedupe_params(api: Json) -> list[Json]:
    """listApis lists some parameters twice; OpenAPI requires them to be unique."""
    seen: dict[str, Json] = {}
    for param in api.get("params") or []:
        name = param["name"]
        if name in RESERVED_PARAMETERS:
            logger.warning("%s declares the reserved parameter %r, skipping it", api["name"], name)
            continue
        if name in seen:
            # Keep the first description, but never lose a "required" flag.
            seen[name]["required"] = seen[name].get("required") or param.get("required")
            continue
        seen[name] = dict(param)
    return list(seen.values())


def build_payload_schema(
    api: Json,
    signature: str,
    registry: SchemaRegistry,
    response_key: tuple[str, bool] | None,
) -> Schema:
    """Schema for the body inside the "<command>response" envelope.

    listApis documents the *entity* a command deals with, never the envelope
    around it. CloudStack then returns that entity either directly (delete-style
    commands), nested under a command specific key (``{"zone": {...}}``), or as a
    counted array (``{"count": 1, "zone": [...]}``). The key is not part of
    listApis, so unless it was resolved by probing a live endpoint the schema
    stays open enough to validate all three renderings.
    """
    payload = registry.ref(signature)
    count_property: Schema = {"type": "integer", "description": "Total number of matching entities."}

    if response_key:
        key, is_array = response_key
        properties: dict[str, Schema] = {}
        if is_array:
            properties["count"] = count_property
            properties[key] = {"type": "array", "items": payload}
        else:
            properties[key] = payload
        return {"type": "object", "properties": properties, "additionalProperties": True}

    nested: Schema = {
        "type": "object",
        "properties": {"count": count_property},
        "additionalProperties": {"oneOf": [payload, {"type": "array", "items": payload}]},
    }
    if api["name"].startswith("list"):
        return nested
    return {"oneOf": [payload, nested]}


def build_operation(
    api: Json,
    signature: str,
    registry: SchemaRegistry,
    response_key: tuple[str, bool] | None,
    tag: str,
) -> Json:
    """Build the ``get`` operation object for one CloudStack command."""
    command = api["name"]
    key = envelope_key(command)
    is_async = bool(api.get("isasync"))

    parameters: list[Json] = [{"$ref": "#/components/parameters/response"}]
    parameters += [
        build_parameter(param, registry)
        for param in sorted(dedupe_params(api), key=lambda p: (not p.get("required"), p["name"]))
    ]

    if is_async:
        payload: Schema = {"$ref": "#/components/schemas/AsyncJobStart"}
    else:
        payload = build_payload_schema(api, signature, registry, response_key)

    description = (api.get("description") or "").strip()
    if is_async:
        description = (
            f"{description}\n\nThis command is asynchronous: it returns a `jobid`. "
            "The documented entity is delivered in the `jobresult` of `queryAsyncJobResult`."
        ).strip()

    operation: Json = {"operationId": command, "summary": first_sentence(api.get("description")) or command}
    if description and description != operation["summary"]:
        operation["description"] = description
    operation["tags"] = [tag]
    operation["parameters"] = parameters
    operation["responses"] = {
        "200": {
            "description": f"Successful invocation of `{command}`.",
            "content": {"application/json": {"schema": {"type": "object", "properties": {key: payload}, "required": [key]}}},
        },
        "default": {
            "description": "CloudStack error. The HTTP status repeats the `errorcode` of the body.",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {key: {"$ref": "#/components/schemas/CloudStackError"}},
                        "required": [key],
                    }
                }
            },
        },
    }
    operation["x-cloudstack-command"] = command
    operation["x-cloudstack-async"] = is_async
    if since := api.get("since"):
        operation["x-cloudstack-since"] = since
    if related := related_commands(api.get("related")):
        operation["x-cloudstack-related"] = related
    if is_async:
        operation["x-cloudstack-jobresult-schema"] = registry.ref(signature)["$ref"]
    return operation


def build_document(apis: Iterable[Json], options: GeneratorOptions | None = None) -> Json:
    """Build the complete OpenAPI document from a ``listApis`` catalogue.

    The result is deterministic: the same catalogue and options always produce an
    identical document.
    """
    options = options or GeneratorOptions()
    apis = sorted(apis, key=lambda api: api["name"])

    registry = SchemaRegistry()
    signatures = {api["name"]: registry.add(api.get("response"), api["name"], "top") for api in apis}
    schemas = registry.finalize()

    paths: dict[str, Json] = {}
    tags: Counter[str] = Counter()
    tagger = build_tagger([api["name"] for api in apis])
    for api in apis:
        command = api["name"]
        operation = build_operation(
            api,
            signatures[command],
            registry,
            options.response_keys.get(command),
            tagger(command),
        )
        operation["parameters"].insert(
            0,
            {
                "name": "command",
                "in": "query",
                "description": "API command to invoke.",
                "required": True,
                # "default" repeats "const" so that documentation browsers and
                # generated clients prefill the value instead of leaving the
                # required parameter empty.
                "schema": {"type": "string", "const": command, "default": command},
            },
        )
        tags[operation["tags"][0]] += 1
        paths[f"/{command}"] = {"get": operation}

    document: Json = {"openapi": OPENAPI_VERSION}
    if options.self_uri:
        document["$self"] = options.self_uri
    document["info"] = {
        "title": options.title,
        "summary": "Apache CloudStack API, generated from listApis.",
        "description": DESCRIPTION_HEADER,
        "license": {"name": "Apache License 2.0", "identifier": "Apache-2.0"},
        "version": options.api_version,
    }
    document["servers"] = [
        {
            "url": options.server_url,
            "name": "cloudstack",
            "description": "CloudStack API endpoint, usually the management server plus `/client/api`.",
        }
    ]
    document["security"] = [{"apiKey": [], "signature": []}, {"sessionKey": []}]
    document["tags"] = [
        {"name": name, "description": f"{count} command{'' if count == 1 else 's'} acting on {name}."}
        for name, count in sorted(tags.items())
    ]
    document["paths"] = paths
    document["components"] = {
        "securitySchemes": SECURITY_SCHEMES,
        "parameters": COMMON_PARAMETERS,
        "schemas": {"CloudStackError": ERROR_SCHEMA, "AsyncJobStart": ASYNC_SCHEMA}
        | {name: schemas[name] for name in sorted(schemas)},
    }
    return document


__all__ = [
    "ASYNC_SCHEMA",
    "COMMON_PARAMETERS",
    "DEFAULT_SERVER_URL",
    "DEFAULT_TITLE",
    "ERROR_SCHEMA",
    "OPENAPI_VERSION",
    "RESERVED_PARAMETERS",
    "SECURITY_SCHEMES",
    "GeneratorOptions",
    "build_document",
    "build_operation",
    "build_parameter",
    "build_payload_schema",
    "dedupe_params",
]
