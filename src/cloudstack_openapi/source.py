# Copyright (c) 2026, René Moser <mail@renemoser.net>
# SPDX-License-Identifier: Apache-2.0

"""Obtaining a ``listApis`` catalogue, from a live endpoint or from a file."""

import json
import logging
from os import PathLike
from typing import Any

from ._types import Json
from .errors import DependencyError, SourceError

logger = logging.getLogger(__name__)


def load_listapis(path: str | PathLike[str]) -> list[Json]:
    """Read a catalogue from a captured ``listApis`` response.

    Accepts both the raw response (``{"count": 1, "api": [...]}``) and a bare
    list of command objects.
    """
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    apis = payload.get("api", payload) if isinstance(payload, dict) else payload
    if not isinstance(apis, list) or not apis:
        raise SourceError(f"{path} does not contain a listApis response")
    return apis


def create_client(endpoint: str | None = None) -> Any:
    """Build a ``cs.CloudStack`` client from the usual CloudStack configuration.

    The configuration is read by the ``cs`` library from ``~/.cloudstack.ini`` or
    the ``CLOUDSTACK_*`` environment variables; *endpoint* overrides the endpoint
    it resolves to.
    """
    try:
        from cs import CloudStack, read_config
    except ImportError as exc:  # pragma: no cover - depends on the installed extras
        raise DependencyError(
            "the 'cs' library is required to query a live endpoint; "
            "install it with: pip install 'cloudstack-openapi-ngine[live]'"
        ) from exc

    config = read_config()
    if endpoint:
        config["endpoint"] = endpoint
    return CloudStack(**config)


def fetch_listapis(client: Any) -> list[Json]:
    """Fetch the catalogue of every command the calling account may see."""
    apis = client.listApis().get("api") or []
    if not apis:
        raise SourceError("listApis returned no commands")
    return apis


def fetch_api_version(client: Any) -> str:
    """The CloudStack version of the endpoint, or ``"unknown"``."""
    try:
        version = client.listCapabilities()["capability"]["cloudstackversion"]
    except Exception:
        # The version is cosmetic, and listCapabilities may be denied to the caller.
        logger.debug("listCapabilities did not yield a version", exc_info=True)
        return "unknown"
    return str(version)


def probe_response_keys(client: Any, apis: list[Json]) -> dict[str, tuple[str, bool]]:
    """Resolve the per-command payload key by calling read-only list commands.

    listApis does not expose the key CloudStack nests a payload under, so the
    only way to learn it is to look at a real response. Only ``list*`` commands
    are probed, with no arguments; commands that error or come back empty are
    left unresolved.
    """
    keys: dict[str, tuple[str, bool]] = {}
    for api in apis:
        command = api["name"]
        if not command.startswith("list") or api.get("isasync"):
            continue
        try:
            result = getattr(client, command)()
        except Exception:
            # A failing probe simply teaches us nothing about this command.
            logger.debug("probing %s failed", command, exc_info=True)
            continue
        if not isinstance(result, dict):
            continue
        candidates = [key for key in result if key != "count"]
        if len(candidates) == 1:
            # Not every list command returns a collection: listCapabilities
            # nests a single object under "capability".
            key = candidates[0]
            keys[command] = (key, isinstance(result[key], list))
    return keys


__all__ = [
    "create_client",
    "fetch_api_version",
    "fetch_listapis",
    "load_listapis",
    "probe_response_keys",
]
