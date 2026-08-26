"""Reading append-only JSONL files as a stream of dict records.

Each non-blank line of a JSONL file must decode to a JSON object. Anything
else -- a bare number, a list, malformed JSON -- is a hard error, since a
silently skipped record would make a pipeline's output look correct while
quietly dropping data.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, Iterator


class JSONLError(ValueError):
    """Raised when a line of a JSONL source is not a valid JSON object."""


def _parse_lines(lines: Iterable[str], source: str) -> Iterator[Dict[str, Any]]:
    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            record = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise JSONLError(f"{source}: line {line_number}: invalid JSON ({exc})") from exc
        if not isinstance(record, dict):
            raise JSONLError(
                f"{source}: line {line_number}: record must be a JSON object, "
                f"got {type(record).__name__}"
            )
        yield record


def read_jsonl(path: str) -> Iterator[Dict[str, Any]]:
    """Yield each record of a JSONL file at ``path`` as a dict, in order."""
    with open(path, "r", encoding="utf-8") as handle:
        yield from _parse_lines(handle, str(path))


def parse_jsonl_lines(lines: Iterable[str], source: str = "<lines>") -> Iterator[Dict[str, Any]]:
    """Parse an already-in-memory iterable of raw text lines into records.

    Useful for feeding newly appended lines of a watched file straight into
    a pipeline without re-reading the whole file from disk.
    """
    yield from _parse_lines(lines, source)
