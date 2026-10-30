"""Complete JSON artifacts written with the caller's filesystem permissions."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import Any

from browser_cli import error_codes
from browser_cli.errors import OperationFailedError


def write_json_artifact(path: str | Path, value: Any) -> dict[str, Any]:
    """Atomically replace a JSON file and describe exactly the bytes saved."""
    temporary: Path | None = None
    try:
        # Serialize before touching the destination; invalid values never replace it.
        content = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode(
            "utf-8"
        )
        destination = Path(path).expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            dir=destination.parent, prefix=".browser-cli-", delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    except (OSError, ValueError, TypeError, RecursionError) as exc:
        raise OperationFailedError(
            f"Cannot save JSON artifact: {exc}", error_code=error_codes.OUTPUT_WRITE_FAILED
        ) from exc
    finally:
        if temporary is not None:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)
    result_type = (
        "null"
        if value is None
        else "boolean"
        if isinstance(value, bool)
        else "object"
        if isinstance(value, dict)
        else "array"
        if isinstance(value, (list, tuple))
        else "string"
        if isinstance(value, str)
        else "number"
    )
    return {
        "path": str(destination),
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "result_type": result_type,
    }
