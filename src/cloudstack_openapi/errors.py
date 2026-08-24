# Copyright (c) 2026, René Moser <mail@renemoser.net>
# SPDX-License-Identifier: Apache-2.0

"""Exceptions raised by this package."""


class CloudStackOpenAPIError(Exception):
    """Base class for every error this package raises on its own."""


class SourceError(CloudStackOpenAPIError):
    """A ``listApis`` catalogue could not be obtained or is unusable."""


class DependencyError(CloudStackOpenAPIError):
    """An optional dependency needed for the requested operation is missing."""


__all__ = ["CloudStackOpenAPIError", "DependencyError", "SourceError"]
