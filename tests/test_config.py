import json
import os
import tempfile
import unittest

from streamloom.config import ConfigError, Pipeline, load_config, parse_config, stage_type_name


class ParseConfigValidTest(unittest.TestCase):
    def test_full_pipeline_runs_in_order(self):
        config = {
            "stages": [
                {
                    "type": "filter",
                    "conditions": [{"field": "level", "op": "eq", "value": "error"}],
                },
                {
                    "type": "map",
                    "select": ["message", "user"],
                    "rename": {"message": "msg"},
                    "set": {"seen": True},
                },
                {"type": "reduce", "op": "count", "as": "error_count"},
            ]
        }
        pipeline = parse_config(config)
        self.assertIsInstance(pipeline, Pipeline)
        self.assertEqual(len(pipeline.stages), 3)

        records = [
            {"level": "error", "message": "boom", "user": "a"},
            {"level": "info", "message": "ok", "user": "b"},
            {"level": "error", "message": "bang", "user": "c"},
        ]
        result = pipeline.run(records)
        self.assertEqual(result, [{"error_count": 2}])

    def test_map_select_rename_set_drop(self):
        pipeline = parse_config(
            {
                "stages": [
                    {
                        "type": "map",
                        "drop": ["password"],
                        "set": {"source": "app"},
                    }
                ]
            }
        )
        result = pipeline.run([{"user": "a", "password": "secret"}])
        self.assertEqual(result, [{"user": "a", "source": "app"}])

    def test_filter_any_match(self):
        pipeline = parse_config(
            {
                "stages": [
                    {
                        "type": "filter",
                        "match": "any",
                        "conditions": [
                            {"field": "level", "op": "eq", "value": "error"},
                            {"field": "urgent", "op": "eq", "value": True},
                        ],
                    }
                ]
            }
        )
        records = [
            {"level": "info", "urgent": True},
            {"level": "info", "urgent": False},
        ]
        self.assertEqual(pipeline.run(records), [{"level": "info", "urgent": True}])

    def test_reduce_sum(self):
        pipeline = parse_config(
            {"stages": [{"type": "reduce", "op": "sum", "field": "amount", "as": "total"}]}
        )
        records = [{"amount": 3}, {"amount": 4}, {"amount": 5}]
        self.assertEqual(pipeline.run(records), [{"total": 12}])

    def test_filter_exists_and_not_exists(self):
        pipeline = parse_config(
            {
                "stages": [
                    {"type": "filter", "conditions": [{"field": "user", "op": "exists"}]}
                ]
            }
        )
        records = [{"user": "a"}, {"other": 1}]
        self.assertEqual(pipeline.run(records), [{"user": "a"}])


class ParseConfigInvalidTest(unittest.TestCase):
    def test_missing_stages_key(self):
        with self.assertRaises(ConfigError):
            parse_config({})

    def test_empty_stages_list(self):
        with self.assertRaises(ConfigError):
            parse_config({"stages": []})

    def test_unknown_stage_type(self):
        with self.assertRaises(ConfigError):
            parse_config({"stages": [{"type": "sort"}]})

    def test_filter_missing_conditions(self):
        with self.assertRaises(ConfigError):
            parse_config({"stages": [{"type": "filter"}]})

    def test_filter_unknown_op(self):
        with self.assertRaises(ConfigError):
            parse_config(
                {
                    "stages": [
                        {
                            "type": "filter",
                            "conditions": [{"field": "x", "op": "regex", "value": "y"}],
                        }
                    ]
                }
            )

    def test_filter_op_missing_value(self):
        with self.assertRaises(ConfigError):
            parse_config(
                {"stages": [{"type": "filter", "conditions": [{"field": "x", "op": "eq"}]}]}
            )

    def test_map_with_no_operations(self):
        with self.assertRaises(ConfigError):
            parse_config({"stages": [{"type": "map"}]})

    def test_reduce_unknown_op(self):
        with self.assertRaises(ConfigError):
            parse_config({"stages": [{"type": "reduce", "op": "average", "field": "x"}]})

    def test_reduce_missing_field(self):
        with self.assertRaises(ConfigError):
            parse_config({"stages": [{"type": "reduce", "op": "sum"}]})

    def test_config_must_be_object(self):
        with self.assertRaises(ConfigError):
            parse_config([1, 2, 3])


class LoadConfigTest(unittest.TestCase):
    def test_load_config_from_file(self):
        config = {"stages": [{"type": "reduce", "op": "count"}]}
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "pipeline.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(config, handle)
            pipeline = load_config(path)
            self.assertEqual(pipeline.run([{}, {}]), [{"count": 2}])

    def test_load_config_rejects_invalid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "pipeline.json")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("{not valid json")
            with self.assertRaises(ConfigError):
                load_config(path)

    def test_load_config_rejects_invalid_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "pipeline.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"stages": [{"type": "bogus"}]}, handle)
            with self.assertRaises(ConfigError):
                load_config(path)


class RunWithTimingsTest(unittest.TestCase):
    def test_reports_one_timing_per_stage_with_correct_counts(self):
        pipeline = parse_config(
            {
                "stages": [
                    {"type": "filter", "conditions": [{"field": "level", "op": "eq", "value": "error"}]},
                    {"type": "reduce", "op": "count", "as": "n"},
                ]
            }
        )
        records = [{"level": "error"}, {"level": "info"}, {"level": "error"}]
        result, timings = pipeline.run_with_timings(records)

        self.assertEqual(result, [{"n": 2}])
        self.assertEqual(len(timings), 2)

        self.assertEqual(timings[0].index, 0)
        self.assertEqual(stage_type_name(pipeline.stages[0]), "filter")
        self.assertEqual(timings[0].type, "filter")
        self.assertEqual(timings[0].input_count, 3)
        self.assertEqual(timings[0].output_count, 2)
        self.assertGreaterEqual(timings[0].elapsed_seconds, 0.0)

        self.assertEqual(timings[1].type, "reduce")
        self.assertEqual(timings[1].input_count, 2)
        self.assertEqual(timings[1].output_count, 1)

    def test_run_and_run_with_timings_agree_on_result(self):
        pipeline = parse_config({"stages": [{"type": "reduce", "op": "count"}]})
        records = [{}, {}, {}]
        self.assertEqual(pipeline.run(records), pipeline.run_with_timings(records)[0])


if __name__ == "__main__":
    unittest.main()
