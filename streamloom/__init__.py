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
from .executor import (
    ExecutorError,
    discover_input_files,
    execute,
    load_input_records,
    run_pipeline,
    write_output,
)
from .jsonl import JSONLError, parse_jsonl_lines, read_jsonl

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
]
