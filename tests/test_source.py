# Copyright (c) 2026, René Moser <mail@renemoser.net>
# SPDX-License-Identifier: Apache-2.0

"""Tests for obtaining a listApis catalogue."""

import json
from pathlib import Path
from typing import Any

import pytest

from cloudstack_openapi.errors import SourceError
from cloudstack_openapi.source import (
    create_client,
    fetch_api_version,
    fetch_listapis,
    load_listapis,
    probe_response_keys,
)


class FakeClient:
    """A ``cs.CloudStack`` stand-in: every command is an attribute returning canned data."""

    def __init__(self, responses: dict[str, Any]) -> None:
        self._responses = responses
        self.calls: list[str] = []

    def __getattr__(self, command: str) -> Any:
        def call(**_kwargs: Any) -> Any:
            self.calls.append(command)
            result = self._responses[command]
            if isinstance(result, Exception):
                raise result
            return result

        return call


def test_load_listapis_accepts_a_raw_response(listapis_file: Path) -> None:
    assert [api["name"] for api in load_listapis(listapis_file)][:1] == ["listZones"]


def test_load_listapis_accepts_a_bare_list(tmp_path: Path) -> None:
    path = tmp_path / "apis.json"
    path.write_text(json.dumps([{"name": "listZones"}]), encoding="utf-8")
    assert load_listapis(path) == [{"name": "listZones"}]


@pytest.mark.parametrize("payload", ["{}", "[]", '{"api": []}'])
def test_load_listapis_rejects_an_empty_catalogue(tmp_path: Path, payload: str) -> None:
    path = tmp_path / "apis.json"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(SourceError, match="does not contain a listApis response"):
        load_listapis(path)


def test_fetch_listapis_returns_the_commands() -> None:
    client = FakeClient({"listApis": {"count": 1, "api": [{"name": "listZones"}]}})
    assert fetch_listapis(client) == [{"name": "listZones"}]


def test_fetch_listapis_rejects_an_empty_catalogue() -> None:
    with pytest.raises(SourceError, match="no commands"):
        fetch_listapis(FakeClient({"listApis": {"count": 0}}))


def test_fetch_api_version_reads_list_capabilities() -> None:
    client = FakeClient({"listCapabilities": {"capability": {"cloudstackversion": "4.22.0.0"}}})
    assert fetch_api_version(client) == "4.22.0.0"


def test_fetch_api_version_falls_back_when_the_endpoint_refuses() -> None:
    client = FakeClient({"listCapabilities": RuntimeError("permission denied")})
    assert fetch_api_version(client) == "unknown"


def test_probe_resolves_array_and_singular_payload_keys() -> None:
    client = FakeClient(
        {
            "listZones": {"count": 1, "zone": [{"id": "a"}]},
            # Not every list command returns a collection.
            "listCapabilities": {"capability": {"cloudstackversion": "4.22.0.0"}},
        }
    )
    apis = [{"name": "listZones", "isasync": False}, {"name": "listCapabilities", "isasync": False}]

    assert probe_response_keys(client, apis) == {"listZones": ("zone", True), "listCapabilities": ("capability", False)}


def test_probe_skips_non_list_and_async_commands() -> None:
    client = FakeClient({})
    apis = [
        {"name": "deleteZone", "isasync": False},
        {"name": "listVirtualMachinesMetrics", "isasync": True},
    ]
    assert probe_response_keys(client, apis) == {}
    assert client.calls == []


def test_probe_leaves_failing_or_ambiguous_commands_unresolved() -> None:
    client = FakeClient(
        {
            "listFailing": RuntimeError("boom"),
            "listEmpty": {"count": 0},
            "listAmbiguous": {"zone": [], "extra": []},
            "listNotAnObject": ["nope"],
        }
    )
    apis = [{"name": name, "isasync": False} for name in client._responses]

    assert probe_response_keys(client, apis) == {}
    assert client.calls == ["listFailing", "listEmpty", "listAmbiguous", "listNotAnObject"]


def test_create_client_uses_the_cs_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    import cs

    monkeypatch.setattr(
        cs, "read_config", lambda *a, **kw: {"endpoint": "https://configured/client/api", "key": "k", "secret": "s"}
    )
    client = create_client()
    assert client.endpoint == "https://configured/client/api"


def test_create_client_endpoint_overrides_the_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    import cs

    monkeypatch.setattr(
        cs, "read_config", lambda *a, **kw: {"endpoint": "https://configured/client/api", "key": "k", "secret": "s"}
    )
    client = create_client("https://override/client/api")
    assert client.endpoint == "https://override/client/api"
