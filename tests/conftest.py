# Copyright (c) 2026, René Moser <mail@renemoser.net>
# SPDX-License-Identifier: Apache-2.0

"""Shared fixtures: a small but representative ``listApis`` catalogue."""

import json
from pathlib import Path
from typing import Any

import pytest

from cloudstack_openapi import GeneratorOptions, build_document

#: The response object every zone-shaped command returns.
ZONE_FIELDS: list[dict[str, Any]] = [
    {"name": "id", "type": "uuid", "description": "ID of the zone"},
    {"name": "name", "type": "string", "description": "name of the zone"},
    {"name": "created", "type": "date", "description": "when the zone was created"},
    {"name": "allocationstate", "type": "allocationstate", "description": "allocation state"},
    {
        "name": "tags",
        "type": "list",
        "description": "the list of resource tags",
        "response": [
            {"name": "key", "type": "string", "description": "tag key"},
            {"name": "value", "type": "string", "description": "tag value"},
        ],
    },
    # listApis pads response field lists with empty objects.
    {},
]

#: The response object every virtual machine shaped command returns.
VIRTUAL_MACHINE_FIELDS: list[dict[str, Any]] = [
    {"name": "id", "type": "uuid", "description": "ID of the virtual machine"},
    {"name": "name", "type": "string", "description": "name of the virtual machine"},
    {"name": "cpunumber", "type": "integer", "description": "number of CPUs"},
    {"name": "memory", "type": "long", "description": "memory in MB"},
    {"name": "details", "type": "map", "description": "vm details"},
    {"name": "downloaddetails", "type": "set", "description": "download progress detail"},
    {
        "name": "nic",
        "type": "list",
        "description": "the list of nics",
        "response": [
            {"name": "id", "type": "uuid", "description": "ID of the nic"},
            {"name": "ipaddress", "type": "string", "description": "IP address"},
        ],
    },
]

SUCCESS_FIELDS: list[dict[str, Any]] = [
    {"name": "success", "type": "boolean", "description": "true if the operation succeeded"},
    {"name": "displaytext", "type": "string", "description": "any text associated with the success"},
]


@pytest.fixture
def apis() -> list[dict[str, Any]]:
    """A catalogue exercising sync, async, list, delete and duplicate-parameter cases."""
    return [
        {
            "name": "listZones",
            "description": "Lists zones. Only zones visible to the caller are returned.",
            "isasync": False,
            "since": "3.0.0",
            "related": "createZone,updateZone,createZone",
            "params": [
                {"name": "id", "type": "uuid", "description": "the ID of the zone", "required": False},
                {"name": "name", "type": "string", "description": "the name of the zone", "length": 255},
                {"name": "ids", "type": "list", "description": "the IDs of the zones", "related": "listZones"},
                {"name": "tags", "type": "map", "description": "List by resource tags"},
                {"name": "available", "type": "boolean", "description": "true if the zone is available"},
                # listApis lists some parameters twice; the required flag must survive.
                {"name": "id", "type": "uuid", "description": "duplicate", "required": True},
                # Injected by the generator, so it must be dropped.
                {"name": "response", "type": "string", "description": "response format"},
            ],
            "response": ZONE_FIELDS,
        },
        {
            "name": "updateZone",
            "description": "Updates a zone.",
            "isasync": False,
            "params": [{"name": "id", "type": "uuid", "description": "the ID of the zone", "required": True}],
            "response": ZONE_FIELDS,
        },
        {
            "name": "deleteZone",
            "description": "Deletes a zone.",
            "isasync": False,
            "params": [{"name": "id", "type": "uuid", "description": "the ID of the zone", "required": True}],
            "response": SUCCESS_FIELDS,
        },
        {
            "name": "listVirtualMachines",
            "description": "List the virtual machines owned by the account.",
            "isasync": False,
            "params": [{"name": "id", "type": "uuid", "description": "the ID of the virtual machine"}],
            "response": VIRTUAL_MACHINE_FIELDS,
        },
        {
            "name": "deployVirtualMachine",
            "description": "Creates and automatically starts a virtual machine based on a service offering.",
            "isasync": True,
            "since": "4.1.0",
            "params": [
                {"name": "serviceofferingid", "type": "uuid", "description": "the offering", "required": True},
                {"name": "displayname", "type": "string", "description": "the display name", "length": 255},
            ],
            "response": VIRTUAL_MACHINE_FIELDS,
        },
        {
            "name": "destroyVirtualMachine",
            "description": "Destroys a virtual machine.",
            "isasync": True,
            "params": [{"name": "id", "type": "uuid", "description": "the ID", "required": True}],
            "response": VIRTUAL_MACHINE_FIELDS,
        },
        {
            "name": "addNicToVirtualMachine",
            "description": "Adds a NIC to a virtual machine.",
            "isasync": True,
            "params": [{"name": "virtualmachineid", "type": "uuid", "description": "the ID", "required": True}],
            "response": VIRTUAL_MACHINE_FIELDS,
        },
    ]


@pytest.fixture
def document(apis: list[dict[str, Any]]) -> dict[str, Any]:
    """The document built from the :func:`apis` catalogue with default options."""
    return build_document(apis, GeneratorOptions())


@pytest.fixture
def listapis_file(tmp_path: Path, apis: list[dict[str, Any]]) -> Path:
    """The catalogue written out the way ``--dump-listapis`` writes it."""
    path = tmp_path / "listapis.json"
    path.write_text(json.dumps({"count": len(apis), "api": apis}), encoding="utf-8")
    return path
