"""streamloom: a declarative map/filter/reduce pipeline for JSONL streams."""

from .config import (
    ConfigError,
    FilterStage,
    MapStage,
    Pipeline,
    ReduceStage,
    StageTiming,
    load_config,
    parse_config,
    stage_type_name,
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
    run_pipeline_with_timings,
    write_output,
)
from .jsonl import JSONLError, parse_jsonl_lines, read_jsonl
from .status import (
    RunStatus,
    StatusError,
    format_status,
    read_status_report,
    status_report_path,
    write_status_report,
)
from .watcher import snapshot, watch

__version__ = "0.1.0"

__all__ = [
    "ConfigError",
    "FilterStage",
    "MapStage",
    "Pipeline",
    "ReduceStage",
    "StageTiming",
    "load_config",
    "parse_config",
    "stage_type_name",
    "JSONLError",
    "parse_jsonl_lines",
    "read_jsonl",
    "ExecutorError",
    "discover_input_files",
    "execute",
    "load_input_records",
    "run_pipeline",
    "run_pipeline_with_timings",
    "write_output",
    "snapshot",
    "watch",
    "DiffEntry",
    "diff_report_path",
    "diff_values",
    "format_diff",
    "read_previous_output",
    "write_diff_report",
    "RunStatus",
    "StatusError",
    "format_status",
    "read_status_report",
    "status_report_path",
    "write_status_report",
]
