"""Run-status reporting: what the last run did, per-stage timings, and record counts.

Every call to :func:`streamloom.executor.execute` writes a small JSON report
to ``status_report_path(output_path)`` describing what happened: when the run
started, how long it took overall and per pipeline stage, and how many
records went in and came out. ``python -m streamloom status`` reads that file
back and prints it -- there is no separate daemon state to keep in sync, the
report *is* the state, written by the same run it describes.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


class StatusError(ValueError):
    """Raised when a status report file exists but cannot be read."""


@dataclass(frozen=True)
class RunStatus:
    """A snapshot of one ``execute`` run, as written to a status report file."""

    config_path: str
    input_dir: str
    output_path: str
    started_at: str  # ISO 8601 timestamp, UTC
    duration_seconds: float
    input_record_count: int
    output_record_count: int
    stages: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


_REQUIRED_FIELDS = (
    "config_path",
    "input_dir",
    "output_path",
    "started_at",
    "duration_seconds",
    "input_record_count",
    "output_record_count",
    "stages",
)


def status_report_path(output_path: str) -> str:
    """Return the path a run-status report for ``output_path`` is written to."""
    return f"{output_path}.status.json"


def write_status_report(status: RunStatus, path: str) -> None:
    """Write ``status`` to ``path`` as formatted JSON."""
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(status.to_dict(), handle, indent=2, sort_keys=True)
        handle.write("\n")


def read_status_report(output_path: str) -> Optional[RunStatus]:
    """Read the run-status report for ``output_path``, or ``None`` if there is none.

    A missing report means ``execute`` has never been run for this output
    path -- that is reported as "no run recorded" rather than an error, the
    same way :func:`streamloom.diff.read_previous_output` treats a missing
    output file as "no previous run" instead of raising.
    """
    path = status_report_path(output_path)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise StatusError(f"{path}: could not read status report ({exc})") from exc

    if not isinstance(data, dict) or any(key not in data for key in _REQUIRED_FIELDS):
        raise StatusError(f"{path}: malformed status report")

    return RunStatus(
        config_path=data["config_path"],
        input_dir=data["input_dir"],
        output_path=data["output_path"],
        started_at=data["started_at"],
        duration_seconds=data["duration_seconds"],
        input_record_count=data["input_record_count"],
        output_record_count=data["output_record_count"],
        stages=data["stages"],
    )


def format_status(status: RunStatus) -> str:
    """Render a :class:`RunStatus` as a human-readable, multi-line report."""
    lines = [
        f"last run:  {status.started_at}",
        f"config:    {status.config_path}",
        f"input:     {status.input_dir} ({status.input_record_count} record(s))",
        f"output:    {status.output_path} ({status.output_record_count} record(s))",
        f"duration:  {status.duration_seconds:.3f}s",
        "stages:",
    ]
    if not status.stages:
        lines.append("  (none)")
    for stage in status.stages:
        lines.append(
            f"  [{stage['index']}] {stage['type']}: "
            f"{stage['input_count']} -> {stage['output_count']} record(s) "
            f"in {stage['elapsed_seconds']:.3f}s"
        )
    return "\n".join(lines) + "\n"
