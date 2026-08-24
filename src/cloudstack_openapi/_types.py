# Copyright (c) 2026, René Moser <mail@renemoser.net>
# SPDX-License-Identifier: Apache-2.0

"""Type aliases shared across the package."""

from typing import Any, Literal

#: A JSON object as it appears in a ``listApis`` response.
Json = dict[str, Any]

#: An OpenAPI schema fragment.
Schema = dict[str, Any]

#: Where a response object shape was found: at the top level of a command's
#: response, or nested inside another object.
Kind = Literal["top", "nested"]

__all__ = ["Json", "Kind", "Schema"]
