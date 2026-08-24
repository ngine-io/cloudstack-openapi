# Copyright (c) 2026, René Moser <mail@renemoser.net>
# SPDX-License-Identifier: Apache-2.0

"""Tests for rendering the document."""

import io
import json
from typing import Any

import pytest
import yaml

from cloudstack_openapi.serialization import dump, dumps


def test_json_output_round_trips(document: dict[str, Any]) -> None:
    rendered = dumps(document, "json")
    assert rendered.endswith("\n")
    assert json.loads(rendered) == document


def test_yaml_output_round_trips(document: dict[str, Any]) -> None:
    assert yaml.safe_load(dumps(document, "yaml")) == document


def test_yaml_keeps_the_document_order(document: dict[str, Any]) -> None:
    loaded = yaml.safe_load(dumps(document, "yaml"))
    assert list(loaded) == list(document)


def test_yaml_renders_multiline_strings_as_block_scalars(document: dict[str, Any]) -> None:
    rendered = dumps(document, "yaml")
    assert "description: |" in rendered


def test_yaml_is_the_default_format(document: dict[str, Any]) -> None:
    assert dumps(document) == dumps(document, "yaml")


def test_dump_writes_to_a_stream(document: dict[str, Any]) -> None:
    stream = io.StringIO()
    dump(document, stream, "json")
    assert json.loads(stream.getvalue()) == document


def test_rendering_is_deterministic(document: dict[str, Any]) -> None:
    assert dumps(document, "yaml") == dumps(document, "yaml")
    assert dumps(document, "json") == dumps(document, "json")


def test_unknown_format_is_rejected(document: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="unsupported format"):
        dumps(document, "toml")  # type: ignore[arg-type]
