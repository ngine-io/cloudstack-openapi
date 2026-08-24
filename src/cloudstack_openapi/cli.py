# Copyright (c) 2026, René Moser <mail@renemoser.net>
# SPDX-License-Identifier: Apache-2.0

"""Command line interface of ``cloudstack-openapi``."""

import argparse
import json
import logging
import sys
from typing import Any

from ._types import Json
from ._version import __version__
from .document import (
    DEFAULT_SERVER_URL,
    DEFAULT_TITLE,
    OPENAPI_VERSION,
    GeneratorOptions,
    build_document,
)
from .errors import CloudStackOpenAPIError
from .serialization import Format, dump
from .source import (
    create_client,
    fetch_api_version,
    fetch_listapis,
    load_listapis,
    probe_response_keys,
)

PROGRAM = "cloudstack-openapi"

logger = logging.getLogger("cloudstack_openapi")


def build_parser() -> argparse.ArgumentParser:
    """The argument parser, exposed for documentation and tests."""
    parser = argparse.ArgumentParser(
        prog=PROGRAM,
        description=f"Generate an OpenAPI {OPENAPI_VERSION} document from the CloudStack listApis command.",
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--from-api", action="store_true", help="query a live endpoint (default)")
    source.add_argument("--from-json", metavar="FILE", help="read a saved listApis response instead of querying")
    parser.add_argument("--endpoint", help="override the endpoint from the cs configuration")
    parser.add_argument("--dump-listapis", metavar="FILE", help="also write the raw listApis response to FILE")
    parser.add_argument("-o", "--output", metavar="FILE", help="write the document to FILE (default: stdout)")
    parser.add_argument("--format", choices=["yaml", "json"], help="output format (default: from --output, else yaml)")
    parser.add_argument("--server-url", default=DEFAULT_SERVER_URL, help="server URL to advertise")
    parser.add_argument("--title", default=DEFAULT_TITLE, help="info.title of the document")
    parser.add_argument(
        "--api-version",
        help="info.version (default: cloudstackversion of the endpoint, else 'unknown')",
    )
    parser.add_argument("--self", dest="self_uri", metavar="URI", help="set the OpenAPI 3.2 $self field")
    parser.add_argument(
        "--probe-response-keys",
        action="store_true",
        help="call read-only list commands on the endpoint to resolve payload keys exactly (live sources only)",
    )
    parser.add_argument("-q", "--quiet", action="store_true", help="suppress progress and warning messages")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def configure_logging(quiet: bool = False) -> None:
    """Send this package's progress and warning messages to stderr.

    Only the package logger is configured; the root logger is left alone so that
    an application embedding the library keeps control of its own logging.
    """
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(f"{PROGRAM}: %(message)s"))
    logger.handlers[:] = [handler]
    logger.setLevel(logging.ERROR if quiet else logging.INFO)


def _resolve_source(args: argparse.Namespace) -> tuple[Any, list[Json]]:
    if args.from_json:
        if args.probe_response_keys:
            raise CloudStackOpenAPIError("--probe-response-keys needs a live endpoint and cannot be combined with --from-json")
        return None, load_listapis(args.from_json)
    client = create_client(args.endpoint)
    return client, fetch_listapis(client)


def _resolve_format(args: argparse.Namespace) -> Format:
    if args.format:
        return "json" if args.format == "json" else "yaml"
    return "json" if (args.output or "").endswith(".json") else "yaml"


def main(argv: list[str] | None = None) -> int:
    """Entry point of the ``cloudstack-openapi`` command."""
    args = build_parser().parse_args(argv)
    configure_logging(quiet=args.quiet)

    try:
        client, apis = _resolve_source(args)

        if args.dump_listapis:
            with open(args.dump_listapis, "w", encoding="utf-8") as handle:
                json.dump({"count": len(apis), "api": apis}, handle, indent=2, sort_keys=True)

        options = GeneratorOptions(
            server_url=args.server_url,
            title=args.title,
            api_version=args.api_version or (fetch_api_version(client) if client is not None else "unknown"),
            self_uri=args.self_uri,
            response_keys=probe_response_keys(client, apis) if args.probe_response_keys else {},
        )

        document = build_document(apis, options)
        fmt = _resolve_format(args)

        if args.output:
            with open(args.output, "w", encoding="utf-8") as handle:
                dump(document, handle, fmt)
            logger.info(
                "%d commands, %d schemas, %d payload keys resolved -> %s",
                len(apis),
                len(document["components"]["schemas"]),
                len(options.response_keys),
                args.output,
            )
        else:
            dump(document, sys.stdout, fmt)
    except CloudStackOpenAPIError as exc:
        sys.stderr.write(f"{PROGRAM}: {exc}\n")
        return 1
    except OSError as exc:
        sys.stderr.write(f"{PROGRAM}: {exc}\n")
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
