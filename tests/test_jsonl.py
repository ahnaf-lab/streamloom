import os
import tempfile
import unittest

from streamloom.jsonl import JSONLError, parse_jsonl_lines, read_jsonl


class ReadJsonlTest(unittest.TestCase):
    def test_reads_records_and_skips_blank_lines(self):
        content = '{"a": 1}\n\n{"a": 2}\n'
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "data.jsonl")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(content)
            records = list(read_jsonl(path))
            self.assertEqual(records, [{"a": 1}, {"a": 2}])

    def test_invalid_json_line_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "data.jsonl")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write('{"a": 1}\nnot json\n')
            with self.assertRaises(JSONLError):
                list(read_jsonl(path))

    def test_non_object_line_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "data.jsonl")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("[1, 2, 3]\n")
            with self.assertRaises(JSONLError):
                list(read_jsonl(path))


class ParseJsonlLinesTest(unittest.TestCase):
    def test_parses_in_memory_lines(self):
        lines = ['{"x": 1}', '{"x": 2}']
        self.assertEqual(list(parse_jsonl_lines(lines)), [{"x": 1}, {"x": 2}])

    def test_reports_source_and_line_number_in_error(self):
        with self.assertRaises(JSONLError) as ctx:
            list(parse_jsonl_lines(["{}", "bad"], source="appended-lines"))
        message = str(ctx.exception)
        self.assertIn("appended-lines", message)
        self.assertIn("line 2", message)


if __name__ == "__main__":
    unittest.main()
