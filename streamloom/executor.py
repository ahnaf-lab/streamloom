"""Deterministic execution of a pipeline over a directory of JSONL input.

Given a pipeline config and a directory of ``*.jsonl`` files, :func:`execute`
reads every input file in a fixed order, runs the configured pipeline over
the concatenated records, and writes the result to an output file as a
formatted JSON array. Alongside that file it writes a structural diff
against whatever was previously at the output path, so the effect of an
edit -- to the config, or to the input -- is visible immediately.

The output is written deterministically -- same stages, same input bytes,
same output bytes every time -- because the diff against the previous run
is only meaningful if unrelated formatting noise can never appear in it.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import List, Tuple

from .config import Pipeline, Record, StageTiming, load_config
from .diff import diff_report_path, read_previous_output, write_diff_report
from .jsonl import read_jsonl
from .status import RunStatus, status_report_path, write_status_report


class ExecutorError(ValueError):
    """Raised when the executor cannot find or read its input."""


def discover_input_files(input_dir: str) -> List[str]:
    """Return the ``*.jsonl`` files directly inside ``input_dir``, sorted by name.

    Sorting by filename (rather than trusting directory-listing order, which
    varies by OS and filesystem) is what makes concatenation of multiple
    input files deterministic.
    """
    if not os.path.isdir(input_dir):
        raise ExecutorError(f"{input_dir}: not a directory")
    names = sorted(name for name in os.listdir(input_dir) if name.endswith(".jsonl"))
    return [os.path.join(input_dir, name) for name in names]


def load_input_records(input_dir: str) -> List[Record]:
    """Read every ``*.jsonl`` file in ``input_dir``, in sorted-filename order.

    Records within a file keep their on-disk order; files are concatenated
    in the order returned by :func:`discover_input_files`.
    """
    records: List[Record] = []
    for path in discover_input_files(input_dir):
        records.extend(read_jsonl(path))
    return records


def format_output(records: List[Record]) -> str:
    """Render pipeline output as a stable, human-diffable JSON document.

    Keys are sorted and indentation is fixed so that two runs over identical
    input produce byte-identical text.
    """
    return json.dumps(records, indent=2, sort_keys=True) + "\n"


def write_output(records: List[Record], output_path: str) -> None:
    """Write ``records`` to ``output_path`` using :func:`format_output`."""
    with open(output_path, "w", encoding="utf-8") as handle:
        handle.write(format_output(records))


def run_pipeline(pipeline: Pipeline, input_dir: str) -> List[Record]:
    """Run ``pipeline`` over every record in ``input_dir`` and return the result."""
    records = load_input_records(input_dir)
    return pipeline.run(records)


def run_pipeline_with_timings(
    pipeline: Pipeline, input_dir: str
) -> Tuple[List[Record], List[StageTiming]]:
    """Like :func:`run_pipeline`, but also return per-stage timings and counts."""
    records = load_input_records(input_dir)
    return pipeline.run_with_timings(records)


def execute(config_path: str, input_dir: str, output_path: str) -> List[Record]:
    """Load a config, run it over ``input_dir``, and write ``output_path``.

    Before ``output_path`` is overwritten, whatever is already there is read
    and diffed against the new result; the report is written to
    ``diff_report_path(output_path)``. Reading the previous output has to
    happen before the write, or "previous" and "new" would already be the
    same file.

    A run-status report is also written to ``status_report_path(output_path)``,
    recording when the run started, how long it took overall and per stage,
    and how many records went in and came out -- what ``python -m streamloom
    status`` reads back.

    Returns the result records so callers (tests, the CLI) can inspect them
    without re-reading the output file.
    """
    started_at = datetime.now(timezone.utc)
    run_start = time.perf_counter()

    pipeline = load_config(config_path)
    result, timings = run_pipeline_with_timings(pipeline, input_dir)
    input_count = timings[0].input_count if timings else len(result)

    previous = read_previous_output(output_path)
    write_output(result, output_path)
    write_diff_report(previous, result, diff_report_path(output_path))

    duration_seconds = time.perf_counter() - run_start
    status = RunStatus(
        config_path=config_path,
        input_dir=input_dir,
        output_path=output_path,
        started_at=started_at.isoformat(),
        duration_seconds=duration_seconds,
        input_record_count=input_count,
        output_record_count=len(result),
        stages=[
            {
                "index": t.index,
                "type": t.type,
                "input_count": t.input_count,
                "output_count": t.output_count,
                "elapsed_seconds": t.elapsed_seconds,
            }
            for t in timings
        ],
    )
    write_status_report(status, status_report_path(output_path))

    return result
