"""Bounded reads and atomic output replacement for explicit study files."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from .basic_dynamics import decode_json


def read_json_bounded(path: Path, *, maximum_bytes: int) -> Any:
    """Limit the actual read even if a file grows while being opened."""
    with path.open("rb") as stream:
        return decode_json(
            stream.read(maximum_bytes + 1), maximum_bytes=maximum_bytes
        )


def write_text_atomic(path: Path, text: str) -> None:
    """Leave prior evidence intact when writing or replacement fails."""
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    try:
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
