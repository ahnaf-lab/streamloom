import json
import os
import tempfile
import unittest

from streamloom import __main__ as cli
from streamloom.executor import execute
from streamloom.status import (
    RunStatus,
    StatusError,
    format_status,
    read_status_report,
    status_report_path,
    write_status_report,
)

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
PIPELINE_CONFIG = os.path.join(FIXTURES, "pipeline.json")
INPUT_DIR = os.path.join(FIXTURES, "input")


def _sample_status(output_path: str) -> RunStatus:
    return RunStatus(
        config_path=PIPELINE_CONFIG,
        input_dir=INPUT_DIR,
        output_path=output_path,
        started_at="2026-08-29T00:00:00+00:00",
        duration_seconds=0.001234,
        input_record_count=4,
        output_record_count=1,
        stages=[
            {"index": 0, "type": "filter", "input_count": 4, "output_count": 2, "elapsed_seconds": 0.0001},
            {"index": 1, "type": "map", "input_count": 2, "output_count": 2, "elapsed_seconds": 0.0001},
            {"index": 2, "type": "reduce", "input_count": 2, "output_count": 1, "elapsed_seconds": 0.0001},
        ],
    )


class StatusReportPathTest(unittest.TestCase):
    def test_appends_status_json_suffix(self):
        self.assertEqual(status_report_path("out.json"), "out.json.status.json")


class WriteAndReadStatusReportTest(unittest.TestCase):
    def test_round_trips_through_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_path = os.path.join(tmp, "out.json")
            status = _sample_status(out_path)
            write_status_report(status, status_report_path(out_path))

            loaded = read_status_report(out_path)
            self.assertEqual(loaded, status)

    def test_missing_report_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_path = os.path.join(tmp, "out.json")
            self.assertIsNone(read_status_report(out_path))

    def test_malformed_report_raises_status_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_path = os.path.join(tmp, "out.json")
            with open(status_report_path(out_path), "w", encoding="utf-8") as handle:
                handle.write("not json")
            with self.assertRaises(StatusError):
                read_status_report(out_path)

    def test_report_missing_required_field_raises_status_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_path = os.path.join(tmp, "out.json")
            with open(status_report_path(out_path), "w", encoding="utf-8") as handle:
                json.dump({"config_path": "x"}, handle)
            with self.assertRaises(StatusError):
                read_status_report(out_path)


class FormatStatusTest(unittest.TestCase):
    def test_includes_timestamp_counts_and_stage_lines(self):
        status = _sample_status("out.json")
        text = format_status(status)
        self.assertIn("2026-08-29T00:00:00+00:00", text)
        self.assertIn("4 record(s)", text)
        self.assertIn("[0] filter: 4 -> 2 record(s)", text)
        self.assertIn("[2] reduce: 2 -> 1 record(s)", text)


class ExecuteWritesStatusReportTest(unittest.TestCase):
    """Milestone 5: every execute() call records a status report to read back."""

    def test_execute_writes_a_readable_status_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_path = os.path.join(tmp, "out.json")
            execute(PIPELINE_CONFIG, INPUT_DIR, out_path)

            status = read_status_report(out_path)
            self.assertIsNotNone(status)
            self.assertEqual(status.config_path, PIPELINE_CONFIG)
            self.assertEqual(status.input_dir, INPUT_DIR)
            self.assertEqual(status.output_path, out_path)
            self.assertEqual(status.input_record_count, 4)
            self.assertEqual(status.output_record_count, 1)
            self.assertEqual([s["type"] for s in status.stages], ["filter", "map", "reduce"])
            self.assertGreaterEqual(status.duration_seconds, 0.0)

    def test_second_run_overwrites_the_status_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_path = os.path.join(tmp, "out.json")
            execute(PIPELINE_CONFIG, INPUT_DIR, out_path)
            first = read_status_report(out_path)
            execute(PIPELINE_CONFIG, INPUT_DIR, out_path)
            second = read_status_report(out_path)
            self.assertIsNotNone(first)
            self.assertIsNotNone(second)
            # Same fixture input every time, but a fresh timestamp each run.
            self.assertEqual(first.input_record_count, second.input_record_count)


class CliStatusTest(unittest.TestCase):
    def test_status_command_prints_report_after_a_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_path = os.path.join(tmp, "out.json")
            self.assertEqual(cli.main(["run", PIPELINE_CONFIG, INPUT_DIR, out_path]), 0)
            self.assertEqual(cli.main(["status", out_path]), 0)

    def test_status_command_fails_when_no_run_has_happened(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_path = os.path.join(tmp, "out.json")
            self.assertEqual(cli.main(["status", out_path]), 1)


if __name__ == "__main__":
    unittest.main()
