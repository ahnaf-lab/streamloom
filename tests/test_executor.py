import json
import os
import tempfile
import unittest

from streamloom import __main__ as cli
from streamloom.config import ConfigError
from streamloom.executor import (
    ExecutorError,
    discover_input_files,
    execute,
    format_output,
    load_input_records,
    write_output,
)

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
PIPELINE_CONFIG = os.path.join(FIXTURES, "pipeline.json")
INPUT_DIR = os.path.join(FIXTURES, "input")
EXPECTED_OUTPUT = os.path.join(FIXTURES, "expected_output.json")


class DiscoverInputFilesTest(unittest.TestCase):
    def test_sorted_by_name_and_filtered_to_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("b.jsonl", "a.jsonl", "notes.txt"):
                open(os.path.join(tmp, name), "w", encoding="utf-8").close()
            found = discover_input_files(tmp)
            self.assertEqual([os.path.basename(p) for p in found], ["a.jsonl", "b.jsonl"])

    def test_missing_directory_raises(self):
        with self.assertRaises(ExecutorError):
            discover_input_files("/no/such/directory/at/all")


class LoadInputRecordsTest(unittest.TestCase):
    def test_concatenates_files_in_sorted_order(self):
        records = load_input_records(INPUT_DIR)
        self.assertEqual(
            records,
            [
                {"level": "info", "service": "billing", "message": "invoice sent"},
                {"level": "error", "service": "billing", "message": "payment declined"},
                {"level": "error", "service": "auth", "message": "token expired"},
                {"level": "info", "service": "auth", "message": "login ok"},
            ],
        )


class FormatOutputTest(unittest.TestCase):
    def test_keys_sorted_and_trailing_newline(self):
        text = format_output([{"b": 1, "a": 2}])
        self.assertTrue(text.endswith("\n"))
        self.assertLess(text.index('"a"'), text.index('"b"'))

    def test_matches_json_loadable_round_trip(self):
        records = [{"x": [1, 2, 3]}]
        text = format_output(records)
        self.assertEqual(json.loads(text), records)


class ExecuteOnFixedFixtureTest(unittest.TestCase):
    """Milestone 2: a fixed input fixture must produce a fixed, known output."""

    def test_execute_matches_expected_output_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_path = os.path.join(tmp, "out.json")
            result = execute(PIPELINE_CONFIG, INPUT_DIR, out_path)

            self.assertEqual(result, [{"services_with_errors": ["billing", "auth"]}])

            with open(out_path, "r", encoding="utf-8") as handle:
                actual_text = handle.read()
            with open(EXPECTED_OUTPUT, "r", encoding="utf-8") as handle:
                expected_text = handle.read()
            self.assertEqual(actual_text, expected_text)

    def test_execute_is_byte_for_byte_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_a = os.path.join(tmp, "a.json")
            out_b = os.path.join(tmp, "b.json")
            execute(PIPELINE_CONFIG, INPUT_DIR, out_a)
            execute(PIPELINE_CONFIG, INPUT_DIR, out_b)
            with open(out_a, "rb") as fa, open(out_b, "rb") as fb:
                self.assertEqual(fa.read(), fb.read())

    def test_execute_rejects_invalid_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad_config = os.path.join(tmp, "bad.json")
            with open(bad_config, "w", encoding="utf-8") as handle:
                json.dump({"stages": [{"type": "nonsense"}]}, handle)
            out_path = os.path.join(tmp, "out.json")
            with self.assertRaises(ConfigError):
                execute(bad_config, INPUT_DIR, out_path)


class WriteOutputTest(unittest.TestCase):
    def test_write_output_creates_readable_json_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "out.json")
            write_output([{"n": 1}], path)
            with open(path, "r", encoding="utf-8") as handle:
                self.assertEqual(json.load(handle), [{"n": 1}])


class CliTest(unittest.TestCase):
    def test_main_run_writes_output_and_returns_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_path = os.path.join(tmp, "out.json")
            exit_code = cli.main(["run", PIPELINE_CONFIG, INPUT_DIR, out_path])
            self.assertEqual(exit_code, 0)
            with open(out_path, "r", encoding="utf-8") as handle:
                self.assertEqual(
                    json.load(handle), [{"services_with_errors": ["billing", "auth"]}]
                )

    def test_main_run_reports_error_for_missing_input_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_path = os.path.join(tmp, "out.json")
            exit_code = cli.main(["run", PIPELINE_CONFIG, "/no/such/dir", out_path])
            self.assertEqual(exit_code, 1)

    def test_main_watch_parses_flags_and_invokes_watcher_once(self):
        # Stub cli.watch so this exercises argument wiring and the on_change
        # callback without running a real, unbounded polling loop.
        calls = []
        original_watch = cli.watch

        def fake_watch(config, input_dir, on_change, *, poll_interval, debounce):
            calls.append((config, input_dir, poll_interval, debounce))
            on_change()
            return 1

        cli.watch = fake_watch
        try:
            with tempfile.TemporaryDirectory() as tmp:
                out_path = os.path.join(tmp, "out.json")
                exit_code = cli.main(
                    [
                        "watch",
                        PIPELINE_CONFIG,
                        INPUT_DIR,
                        out_path,
                        "--interval",
                        "0.25",
                        "--debounce",
                        "2.0",
                    ]
                )
                self.assertEqual(exit_code, 0)
                with open(out_path, "r", encoding="utf-8") as handle:
                    self.assertEqual(
                        json.load(handle), [{"services_with_errors": ["billing", "auth"]}]
                    )
        finally:
            cli.watch = original_watch

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0], (PIPELINE_CONFIG, INPUT_DIR, 0.25, 2.0))


if __name__ == "__main__":
    unittest.main()
