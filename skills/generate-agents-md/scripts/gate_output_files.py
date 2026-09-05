from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path


def require_reserved_gate_outputs(*streams):
    """Detect cleanup/recreation of a reserved pathname during execution."""
    for stream in streams:
        try:
            actual = Path(stream.name).lstat()
        except OSError as error:
            raise OSError(f"reserved gate output is missing: {stream.name}") from error
        reserved = os.fstat(stream.fileno())
        if (actual.st_dev, actual.st_ino) != (reserved.st_dev, reserved.st_ino):
            raise OSError(f"reserved gate output was replaced: {stream.name}")


@contextmanager
def exclusive_gate_outputs(output: Path, receipt: Path):
    """Reserve both names before execution. Never replace a prior run's files."""
    output.parent.mkdir(parents=True, exist_ok=True)
    receipt.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as output_stream:
        try:
            receipt_stream = receipt.open('xb')
        except BaseException:
            output.unlink()
            raise
        with receipt_stream:
            # Once execution begins, retain diagnostics and an incomplete receipt
            # after interruption. A retry must select a fresh pair of paths.
            yield output_stream, receipt_stream
            require_reserved_gate_outputs(output_stream, receipt_stream)
