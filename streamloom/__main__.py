"""Command-line entry point.

    python -m streamloom run pipeline.json input_dir/ output.json
    python -m streamloom watch pipeline.json input_dir/ output.json

``run`` performs a single deterministic pass. ``watch`` re-runs the pipeline
whenever the config or input directory changes, debounced so a burst of
rapid edits collapses into one re-run once things settle.
"""

from __future__ import annotations

import argparse
import sys

from .config import ConfigError
from .executor import ExecutorError, execute
from .jsonl import JSONLError
from .watcher import watch


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="streamloom", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser(
        "run", help="run a pipeline config once over a directory of JSONL files"
    )
    run_parser.add_argument("config", help="path to the pipeline config JSON file")
    run_parser.add_argument("input_dir", help="directory containing *.jsonl input files")
    run_parser.add_argument("output", help="path to write the JSON result to")

    watch_parser = subparsers.add_parser(
        "watch",
        help="re-run a pipeline whenever the config or input directory changes",
    )
    watch_parser.add_argument("config", help="path to the pipeline config JSON file")
    watch_parser.add_argument("input_dir", help="directory containing *.jsonl input files")
    watch_parser.add_argument("output", help="path to write the JSON result to")
    watch_parser.add_argument(
        "--interval",
        type=float,
        default=0.5,
        help="how often to poll for changes, in seconds (default: 0.5)",
    )
    watch_parser.add_argument(
        "--debounce",
        type=float,
        default=1.0,
        help="quiet period required before re-running, in seconds (default: 1.0)",
    )

    return parser


def _run_once(config: str, input_dir: str, output: str) -> int:
    try:
        result = execute(config, input_dir, output)
    except (ConfigError, JSONLError, ExecutorError) as exc:
        print(f"streamloom: {exc}", file=sys.stderr)
        return 1
    print(f"wrote {len(result)} record(s) to {output}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        return _run_once(args.config, args.input_dir, args.output)

    if args.command == "watch":
        def on_change() -> None:
            _run_once(args.config, args.input_dir, args.output)

        try:
            watch(
                args.config,
                args.input_dir,
                on_change,
                poll_interval=args.interval,
                debounce=args.debounce,
            )
        except KeyboardInterrupt:
            print("streamloom: stopped", file=sys.stderr)
        return 0

    parser.error(f"unknown command {args.command!r}")  # pragma: no cover
    return 2


if __name__ == "__main__":
    sys.exit(main())
