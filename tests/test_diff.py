import json
import os
import tempfile
import unittest

from streamloom.diff import (
    DiffEntry,
    diff_report_path,
    diff_values,
    format_diff,
    read_previous_output,
    write_diff_report,
)
from streamloom.executor import execute

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
PIPELINE_CONFIG = os.path.join(FIXTURES, "pipeline.json")
INPUT_DIR = os.path.join(FIXTURES, "input")


class DiffValuesTest(unittest.TestCase):
    def test_no_difference_is_empty(self):
        self.assertEqual(diff_values({"a": 1}, {"a": 1}), [])

    def test_changed_scalar_field(self):
        entries = diff_values({"count": 1}, {"count": 2})
        self.assertEqual(entries, [DiffEntry(op="changed", path="$.count", old=1, new=2)])

    def test_added_and_removed_keys(self):
        entries = diff_values({"a": 1}, {"b": 2})
        self.assertIn(DiffEntry(op="removed", path="$.a", old=1), entries)
        self.assertIn(DiffEntry(op="added", path="$.b", new=2), entries)
        self.assertEqual(len(entries), 2)

    def test_list_growth_reports_added_index(self):
        entries = diff_values([{"x": 1}], [{"x": 1}, {"x": 2}])
        self.assertEqual(entries, [DiffEntry(op="added", path="$[1]", new={"x": 2})])

    def test_list_shrink_reports_removed_index(self):
        entries = diff_values([{"x": 1}, {"x": 2}], [{"x": 1}])
        self.assertEqual(entries, [DiffEntry(op="removed", path="$[1]", old={"x": 2})])

    def test_nested_change_has_full_path(self):
        old = [{"services_with_errors": ["billing"]}]
        new = [{"services_with_errors": ["billing", "auth"]}]
        entries = diff_values(old, new)
        self.assertEqual(
            entries, [DiffEntry(op="added", path="$[0].services_with_errors[1]", new="auth")]
        )

    def test_type_change_is_a_single_changed_entry(self):
        entries = diff_values({"a": 1}, [1])
        self.assertEqual(entries, [DiffEntry(op="changed", path="$", old={"a": 1}, new=[1])])

    def test_ordering_is_deterministic(self):
        old = {"z": 1, "a": 1}
        new = {"z": 2, "a": 2}
        entries = diff_values(old, new)
        self.assertEqual([e.path for e in entries], ["$.a", "$.z"])


class FormatDiffTest(unittest.TestCase):
    def test_initial_run_message(self):
        text = format_diff([], is_initial=True)
        self.assertIn("initial run", text)

    def test_no_change_message(self):
        text = format_diff([], is_initial=False)
        self.assertEqual(text, "no change\n")

    def test_renders_each_op_kind(self):
        entries = [
            DiffEntry(op="added", path="$.b", new=2),
            DiffEntry(op="removed", path="$.a", old=1),
            DiffEntry(op="changed", path="$.c", old=1, new=2),
        ]
        text = format_diff(entries, is_initial=False)
        lines = text.splitlines()
        self.assertEqual(lines, ["+ $.b = 2", "- $.a = 1", "~ $.c: 1 -> 2"])


class ReadPreviousOutputTest(unittest.TestCase):
    def test_missing_file_returns_none(self):
        self.assertIsNone(read_previous_output("/no/such/output.json"))

    def test_corrupt_file_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "out.json")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("{not json")
            self.assertIsNone(read_previous_output(path))

    def test_reads_decoded_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "out.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump([{"n": 1}], handle)
            self.assertEqual(read_previous_output(path), [{"n": 1}])


class WriteDiffReportTest(unittest.TestCase):
    def test_writes_report_file_and_returns_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            diff_path = os.path.join(tmp, "out.json.diff")
            text = write_diff_report([{"n": 1}], [{"n": 2}], diff_path)
            with open(diff_path, "r", encoding="utf-8") as handle:
                self.assertEqual(handle.read(), text)
            self.assertIn("~ $[0].n: 1 -> 2", text)

    def test_none_previous_is_initial_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            diff_path = os.path.join(tmp, "out.json.diff")
            text = write_diff_report(None, [{"n": 1}], diff_path)
            self.assertIn("initial run", text)


class DiffReportPathTest(unittest.TestCase):
    def test_appends_diff_suffix(self):
        self.assertEqual(diff_report_path("out.json"), "out.json.diff")


class ExecuteWritesDiffReportTest(unittest.TestCase):
    """Milestone 4: execute() writes a structural diff alongside its output."""

    def test_first_run_reports_no_previous_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_path = os.path.join(tmp, "out.json")
            execute(PIPELINE_CONFIG, INPUT_DIR, out_path)
            with open(diff_report_path(out_path), "r", encoding="utf-8") as handle:
                self.assertIn("initial run", handle.read())

    def test_unchanged_rerun_reports_no_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_path = os.path.join(tmp, "out.json")
            execute(PIPELINE_CONFIG, INPUT_DIR, out_path)
            execute(PIPELINE_CONFIG, INPUT_DIR, out_path)
            with open(diff_report_path(out_path), "r", encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "no change\n")

    def test_edited_input_produces_a_structural_diff(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_dir = os.path.join(tmp, "input")
            os.makedirs(input_dir)
            events_path = os.path.join(input_dir, "events.jsonl")
            out_path = os.path.join(tmp, "out.json")

            with open(events_path, "w", encoding="utf-8") as handle:
                handle.write(json.dumps({"level": "info", "service": "billing"}) + "\n")
            execute(PIPELINE_CONFIG, input_dir, out_path)

            with open(events_path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps({"level": "error", "service": "billing"}) + "\n")
            execute(PIPELINE_CONFIG, input_dir, out_path)

            with open(diff_report_path(out_path), "r", encoding="utf-8") as handle:
                text = handle.read()
            self.assertIn("$[0].services_with_errors", text)
            self.assertIn("billing", text)


if __name__ == "__main__":
    unittest.main()
