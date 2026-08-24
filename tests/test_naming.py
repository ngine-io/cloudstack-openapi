# Copyright (c) 2026, René Moser <mail@renemoser.net>
# SPDX-License-Identifier: Apache-2.0

"""Tests for deriving tags and names from CloudStack command names."""

import pytest

from cloudstack_openapi.naming import (
    build_tagger,
    entity_name,
    entity_of,
    envelope_key,
    first_sentence,
    pascal_case,
    related_commands,
    singularize,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("virtualmachine", "Virtualmachine"),
        ("VirtualMachine", "VirtualMachine"),
        ("service_offering", "ServiceOffering"),
        ("ip-address", "IpAddress"),
        ("", ""),
        ("   ", ""),
    ],
)
def test_pascal_case(value: str, expected: str) -> None:
    assert pascal_case(value) == expected


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("listVirtualMachines", "VirtualMachines"),
        ("disassociateIpAddress", "IpAddress"),
        # "disassociate" must win over the shorter "associate".
        ("associateIpAddress", "IpAddress"),
        ("deployVirtualMachine", "VirtualMachine"),
        # A command that is only a verb, or starts with none, keeps its name.
        ("list", "list"),
        ("login", "login"),
    ],
)
def test_entity_of(command: str, expected: str) -> None:
    assert entity_of(command) == expected


@pytest.mark.parametrize(
    ("entity", "expected"),
    [
        ("VirtualMachines", "VirtualMachine"),
        ("Capabilities", "Capability"),
        ("Addresses", "Address"),
        # Not plurals.
        ("Address", "Address"),
        ("Status", "Status"),
        ("Os", "Os"),
    ],
)
def test_singularize(entity: str, expected: str) -> None:
    assert singularize(entity) == expected


def test_entity_name_folds_plural_and_singular_together() -> None:
    assert entity_name("listVirtualMachines") == entity_name("deployVirtualMachine") == "VirtualMachine"


def test_entity_name_falls_back_to_other() -> None:
    assert entity_name("") == "Other"


def test_tagger_groups_compound_entities_onto_their_anchor() -> None:
    commands = [
        "listVirtualMachines",
        "deployVirtualMachine",
        "destroyVirtualMachine",
        "addNicToVirtualMachine",
        "listZones",
    ]
    tag = build_tagger(commands)

    assert tag("deployVirtualMachine") == "VirtualMachine"
    # Compound entity, folded into the anchor it ends with.
    assert tag("addNicToVirtualMachine") == "VirtualMachine"
    # Below min_shared and matching no anchor: it forms its own group.
    assert tag("listZones") == "Zone"


def test_tagger_needs_min_shared_commands_for_an_anchor() -> None:
    tag = build_tagger(["listVirtualMachines", "addNicToVirtualMachine"])
    assert tag("addNicToVirtualMachine") == "NicToVirtualMachine"


def test_envelope_key_is_lowercased() -> None:
    assert envelope_key("listVirtualMachines") == "listvirtualmachinesresponse"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Lists zones. Only visible ones.", "Lists zones."),
        ("Lists zones\nacross regions", "Lists zones across regions"),
        ("", ""),
        (None, ""),
    ],
)
def test_first_sentence(text: str | None, expected: str) -> None:
    assert first_sentence(text) == expected


def test_first_sentence_is_capped() -> None:
    assert len(first_sentence("word " * 200)) == 250


def test_related_commands_are_deduplicated_and_sorted() -> None:
    assert related_commands("updateZone, createZone ,createZone") == ["createZone", "updateZone"]
    assert related_commands(None) == []
    assert related_commands("") == []
