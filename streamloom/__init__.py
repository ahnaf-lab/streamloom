"""streamloom: a declarative map/filter/reduce pipeline for JSONL streams."""

from .config import (
    ConfigError,
    FilterStage,
    MapStage,
    Pipeline,
    ReduceStage,
    load_config,
    parse_config,
)
from .diff import (
    DiffEntry,
    diff_report_path,
    diff_values,
    format_diff,
    read_previous_output,
    write_diff_report,
)
from .executor import (
    ExecutorError,
    discover_input_files,
    execute,
    load_input_records,
    run_pipeline,
    write_output,
)
from .jsonl import JSONLError, parse_jsonl_lines, read_jsonl
from .watcher import snapshot, watch

__version__ = "0.1.0"

__all__ = [
    "ConfigError",
    "FilterStage",
    "MapStage",
    "Pipeline",
    "ReduceStage",
    "load_config",
    "parse_config",
    "JSONLError",
    "parse_jsonl_lines",
    "read_jsonl",
    "ExecutorError",
    "discover_input_files",
    "execute",
    "load_input_records",
    "run_pipeline",
    "write_output",
    "snapshot",
    "watch",
    "DiffEntry",
    "diff_report_path",
    "diff_values",
    "format_diff",
    "read_previous_output",
    "write_diff_report",
]
