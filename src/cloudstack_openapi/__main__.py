# Copyright (c) 2026, René Moser <mail@renemoser.net>
# SPDX-License-Identifier: Apache-2.0

"""Allows ``python -m cloudstack_openapi``."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
