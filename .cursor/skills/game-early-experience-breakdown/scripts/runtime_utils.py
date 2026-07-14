"""Shared atomic output and CLI error helpers."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, TextIO


def atomic_write_text(path: str | Path, text: str) -> None:
    """Write UTF-8 text and atomically replace the destination on success."""
    destination = Path(path)
    parent = destination.parent
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=parent,
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(text)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, destination)
        temporary_path = None
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass


def error_payload(exc: BaseException) -> dict[str, dict[str, str]]:
    return {
        "error": {
            "type": type(exc).__name__,
            "message": str(exc) or type(exc).__name__,
        }
    }


def emit_json_error(exc: BaseException, stream: TextIO | None = None) -> None:
    """Emit the common JSON error protocol without propagating encoding failures."""
    stream = stream or sys.stderr
    payload: Any = error_payload(exc)
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    try:
        stream.write(text)
    except UnicodeError:
        escaped = json.dumps(payload, ensure_ascii=True, indent=2) + "\n"
        stream.write(escaped)
