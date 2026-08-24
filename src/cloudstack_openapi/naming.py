# Copyright (c) 2026, René Moser <mail@renemoser.net>
# SPDX-License-Identifier: Apache-2.0

"""Turning CloudStack command names into tags, schema names and envelope keys.

CloudStack command names follow a ``<verb><Entity>`` convention that is
consistent enough to derive grouping and naming from, but not part of any
contract. Everything in this module is cosmetic: it affects tag names, schema
names and summaries, never the shape of a request or a response.
"""

import re
from collections import Counter
from collections.abc import Callable, Iterable

# Verbs CloudStack puts in front of the entity name, longest first so that e.g.
# "disassociate" wins over "associate".
COMMAND_VERBS: tuple[str, ...] = (
    "disassociate",
    "deactivate",
    "authorize",
    "reconnect",
    "configure",
    "associate",
    "provision",
    "unregister",
    "unmanage",
    "dedicate",
    "activate",
    "generate",
    "download",
    "register",
    "schedule",
    "validate",
    "release",
    "restore",
    "suspend",
    "migrate",
    "destroy",
    "extract",
    "recover",
    "replace",
    "archive",
    "cancel",
    "change",
    "create",
    "delete",
    "detach",
    "enable",
    "expunge",
    "import",
    "attach",
    "assign",
    "remove",
    "resize",
    "revert",
    "revoke",
    "update",
    "upload",
    "verify",
    "deploy",
    "reboot",
    "reset",
    "scale",
    "start",
    "query",
    "issue",
    "prepare",
    "quiesce",
    "restart",
    "link",
    "lock",
    "mark",
    "move",
    "find",
    "list",
    "copy",
    "add",
    "get",
    "put",
    "run",
    "stop",
    "is",
)


def pascal_case(value: str) -> str:
    """cloudstackName -> CloudstackName, keeping already-cased words intact."""
    value = re.sub(r"[^0-9a-zA-Z]+", " ", value or "").strip()
    if not value:
        return ""
    return "".join(part[:1].upper() + part[1:] for part in value.split(" "))


def entity_of(command: str) -> str:
    """Strip the leading verb off a command name: listVirtualMachines -> VirtualMachines."""
    lowered = command.lower()
    for verb in COMMAND_VERBS:
        if lowered.startswith(verb) and len(command) > len(verb):
            return command[len(verb) :]
    return command


def singularize(entity: str) -> str:
    """listVirtualMachines and deployVirtualMachine must land in the same group."""
    if entity.endswith("ies") and len(entity) > 4:
        return f"{entity.removesuffix('ies')}y"
    if entity.endswith("sses") and len(entity) > 5:
        return entity.removesuffix("es")
    # "Address" and "Status" are not plurals.
    if entity.endswith("s") and not entity.endswith(("ss", "us")) and len(entity) > 2:
        return entity.removesuffix("s")
    return entity


def entity_name(command: str) -> str:
    """The entity a command acts on, as spelled in the command name."""
    return singularize(pascal_case(entity_of(command))) or "Other"


def build_tagger(
    commands: Iterable[str],
    min_shared: int = 3,
    min_anchor_length: int = 5,
) -> Callable[[str], str]:
    """Map each command onto a tag, collapsing compound entities onto a common one.

    Stripping the verb alone splits the API into ~380 groups, half of them with a
    single command: ``addNicToVirtualMachine`` becomes ``NicToVirtualMachine``
    rather than ``VirtualMachine``. Entities shared by several commands are
    therefore used as anchors, and a compound entity is folded into the longest
    anchor it ends with.
    """
    counts = Counter(entity_name(command) for command in commands)
    anchors = sorted(
        (entity for entity, hits in counts.items() if hits >= min_shared and len(entity) >= min_anchor_length),
        key=len,
        reverse=True,
    )

    def tag(command: str) -> str:
        entity = entity_name(command)
        if counts.get(entity, 0) >= min_shared:
            return entity
        lowered = entity.lower()
        for anchor in anchors:
            if lowered != anchor.lower() and lowered.endswith(anchor.lower()):
                return anchor
        return entity

    return tag


def envelope_key(command: str) -> str:
    """CloudStack wraps every body in a "<command>response" key, lower-cased."""
    return f"{command.lower()}response"


def first_sentence(text: str | None) -> str:
    """The first sentence of a description, for use as an operation summary."""
    text = (text or "").strip().replace("\n", " ")
    if not text:
        return ""
    match = re.match(r"^(.+?\.)(\s|$)", text)
    return (match.group(1) if match else text)[:250]


def related_commands(value: str | None) -> list[str]:
    """listApis repeats entries in the comma separated "related" field."""
    if not value:
        return []
    return sorted({name.strip() for name in value.split(",") if name.strip()})


__all__ = [
    "COMMAND_VERBS",
    "build_tagger",
    "entity_name",
    "entity_of",
    "envelope_key",
    "first_sentence",
    "pascal_case",
    "related_commands",
    "singularize",
]
