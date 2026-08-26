"""Command-line entry point: run a pipeline config over a directory once.

    python -m streamloom run pipeline.json input_dir/ output.json

This performs a single deterministic pass -- it does not watch the input
directory for changes; that is a later milestone.
"""

from __future__ import annotations

import argparse
import sys

from .config import ConfigError
from .executor import ExecutorError, execute
from .jsonl import JSONLError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="streamloom", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser(
        "run", help="run a pipeline config once over a directory of JSONL files"
    )
    run_parser.add_argument("config", help="path to the pipeline config JSON file")
    run_parser.add_argument("input_dir", help="directory containing *.jsonl input files")
    run_parser.add_argument("output", help="path to write the JSON result to")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        try:
            result = execute(args.config, args.input_dir, args.output)
        except (ConfigError, JSONLError, ExecutorError) as exc:
            print(f"streamloom: {exc}", file=sys.stderr)
            return 1
        print(f"wrote {len(result)} record(s) to {args.output}")
        return 0

    parser.error(f"unknown command {args.command!r}")  # pragma: no cover
    return 2


if __name__ == "__main__":
    sys.exit(main())
