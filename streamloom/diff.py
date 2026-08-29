"""Structural diff of a pipeline's output against its previous run.

:func:`execute` in :mod:`streamloom.executor` writes its result as formatted
JSON, but a text diff of that formatted JSON is a poor way to see what an
edit actually changed: reordering keys or reflowing whitespace would show up
as noise even though :func:`streamloom.executor.format_output` already keeps
keys sorted and indentation fixed specifically to avoid that. This module
instead diffs the *decoded* JSON values -- dicts, lists, and scalars -- so
the report only ever reflects a real structural change.

Every run compares the value it is about to write against whatever is
already on disk at the output path (read *before* it gets overwritten), and
the result is written to ``<output path>.diff`` alongside the JSON output.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, List, Optional


@dataclass(frozen=True)
class DiffEntry:
    """One structural difference between an old and a new JSON value."""

    op: str  # "added", "removed", or "changed"
    path: str
    old: Any = None
    new: Any = None


def diff_values(old: Any, new: Any, path: str = "$") -> List[DiffEntry]:
    """Recursively diff two JSON-decoded values, returning a sorted entry list.

    Dicts are compared key by key, lists are compared index by index, and
    anything else (including a dict compared against a list, or a scalar
    compared against either) falls back to a single "changed" entry when the
    two values are not equal. Keys and indices are always visited in a fixed
    order so the same pair of inputs produces the same report every time.
    """
    if isinstance(old, dict) and isinstance(new, dict):
        entries: List[DiffEntry] = []
        old_keys = set(old)
        new_keys = set(new)
        for key in sorted(old_keys - new_keys):
            entries.append(DiffEntry(op="removed", path=f"{path}.{key}", old=old[key]))
        for key in sorted(new_keys - old_keys):
            entries.append(DiffEntry(op="added", path=f"{path}.{key}", new=new[key]))
        for key in sorted(old_keys & new_keys):
            entries.extend(diff_values(old[key], new[key], f"{path}.{key}"))
        return entries

    if isinstance(old, list) and isinstance(new, list):
        entries = []
        common = min(len(old), len(new))
        for i in range(common):
            entries.extend(diff_values(old[i], new[i], f"{path}[{i}]"))
        for i in range(common, len(old)):
            entries.append(DiffEntry(op="removed", path=f"{path}[{i}]", old=old[i]))
        for i in range(common, len(new)):
            entries.append(DiffEntry(op="added", path=f"{path}[{i}]", new=new[i]))
        return entries

    if old != new:
        return [DiffEntry(op="changed", path=path, old=old, new=new)]
    return []


def _render_value(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def format_diff(entries: List[DiffEntry], *, is_initial: bool) -> str:
    """Render diff entries as a stable, human-readable report.

    ``is_initial`` marks a run with no previous output to compare against
    (there is nothing on disk yet, or what was there could not be read as
    JSON) -- that is reported explicitly rather than as a wall of "added"
    lines for every field of every record, which would say the same thing
    far less clearly.
    """
    if is_initial:
        return "no previous output -- this is the initial run\n"
    if not entries:
        return "no change\n"

    lines = []
    for entry in entries:
        if entry.op == "added":
            lines.append(f"+ {entry.path} = {_render_value(entry.new)}")
        elif entry.op == "removed":
            lines.append(f"- {entry.path} = {_render_value(entry.old)}")
        else:
            lines.append(f"~ {entry.path}: {_render_value(entry.old)} -> {_render_value(entry.new)}")
    return "\n".join(lines) + "\n"


def diff_report_path(output_path: str) -> str:
    """Return the path a diff report for ``output_path`` is written to."""
    return f"{output_path}.diff"


def read_previous_output(output_path: str) -> Optional[Any]:
    """Read and decode the JSON currently at ``output_path``, if any.

    Returns ``None`` when there is nothing to compare against: the file does
    not exist yet, or it exists but is not valid JSON (for example a run was
    interrupted mid-write). Either way there is no usable baseline, and the
    caller treats that the same as a first run rather than raising.
    """
    if not os.path.exists(output_path):
        return None
    try:
        with open(output_path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None


def write_diff_report(previous: Optional[Any], new: Any, diff_path: str) -> str:
    """Diff ``previous`` against ``new`` and write the report to ``diff_path``.

    ``previous`` should come from :func:`read_previous_output`, called
    *before* the new output is written -- otherwise "previous" and "new"
    would already be identical. Returns the report text.
    """
    if previous is None:
        text = format_diff([], is_initial=True)
    else:
        entries = diff_values(previous, new)
        text = format_diff(entries, is_initial=False)
    with open(diff_path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return text
