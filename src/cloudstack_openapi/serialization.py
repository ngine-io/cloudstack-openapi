# Copyright (c) 2026, René Moser <mail@renemoser.net>
# SPDX-License-Identifier: Apache-2.0

"""Rendering the document as YAML or JSON."""

import json
from typing import Literal, TextIO

from ._types import Json
from .errors import DependencyError

Format = Literal["yaml", "json"]


def dump(document: Json, stream: TextIO, fmt: Format = "yaml") -> None:
    """Write *document* to *stream* in the requested format."""
    if fmt == "json":
        json.dump(document, stream, indent=2)
        stream.write("\n")
        return
    if fmt != "yaml":
        raise ValueError(f"unsupported format {fmt!r}")

    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - depends on the installed extras
        raise DependencyError(
            "PyYAML is required for YAML output; install it with: "
            "pip install 'cloudstack-openapi-ngine[yaml]', or use the JSON format"
        ) from exc

    class Dumper(yaml.SafeDumper):
        """Renders multi-line strings as block scalars so descriptions stay readable."""

    def represent_str(dumper: yaml.SafeDumper, data: str) -> yaml.ScalarNode:
        style = "|" if "\n" in data else None
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)

    Dumper.add_representer(str, represent_str)
    yaml.dump(
        document,
        stream,
        Dumper=Dumper,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
        width=1000000,
    )


def dumps(document: Json, fmt: Format = "yaml") -> str:
    """Render *document* and return it as a string."""
    import io

    buffer = io.StringIO()
    dump(document, buffer, fmt)
    return buffer.getvalue()


__all__ = ["Format", "dump", "dumps"]
