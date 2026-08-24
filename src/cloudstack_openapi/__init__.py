# Copyright (c) 2026, René Moser <mail@renemoser.net>
# SPDX-License-Identifier: Apache-2.0

"""Generate an OpenAPI 3.2 document from the Apache CloudStack ``listApis`` endpoint.

CloudStack describes itself through ``listApis``, which returns a bespoke,
non-standard catalogue of every API command, its request parameters and its
response fields. This package translates that catalogue into an OpenAPI 3.2.0
document that can be fed to documentation browsers and client generators.

The typical entry point is :func:`build_document`::

    from cloudstack_openapi import GeneratorOptions, build_document, dumps

    document = build_document(apis, GeneratorOptions(server_url=url))
    print(dumps(document, "yaml"))
"""

from ._types import Json, Kind, Schema
from ._version import __version__
from .document import (
    OPENAPI_VERSION,
    GeneratorOptions,
    build_document,
    build_operation,
    build_parameter,
)
from .errors import CloudStackOpenAPIError, DependencyError, SourceError
from .schemas import SchemaRegistry
from .serialization import dump, dumps
from .source import (
    create_client,
    fetch_api_version,
    fetch_listapis,
    load_listapis,
    probe_response_keys,
)

__all__ = [
    "OPENAPI_VERSION",
    "CloudStackOpenAPIError",
    "DependencyError",
    "GeneratorOptions",
    "Json",
    "Kind",
    "Schema",
    "SchemaRegistry",
    "SourceError",
    "__version__",
    "build_document",
    "build_operation",
    "build_parameter",
    "create_client",
    "dump",
    "dumps",
    "fetch_api_version",
    "fetch_listapis",
    "load_listapis",
    "probe_response_keys",
]
