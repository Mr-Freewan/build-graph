"""Console helpers shared by the CLI entry points."""

import sys


def ensure_utf8_stdout() -> None:
    """Reconfigure stdout/stderr to UTF-8 on Windows (idempotent).

    The legacy Windows console defaults to a locale codepage; box-drawing
    and emoji output would raise UnicodeEncodeError without this.
    """
    if sys.platform != "win32":
        return
    for stream in (sys.stdout, sys.stderr):
        # Replaced streams (pytest capture, pipes) may lack reconfigure().
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
