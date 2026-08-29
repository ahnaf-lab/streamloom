import os
import tempfile
import unittest

from streamloom.watcher import snapshot, watch

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
PIPELINE_CONFIG = os.path.join(FIXTURES, "pipeline.json")
INPUT_DIR = os.path.join(FIXTURES, "input")


class SnapshotTest(unittest.TestCase):
    def test_snapshot_includes_config_and_jsonl_files(self):
        fp = snapshot(PIPELINE_CONFIG, INPUT_DIR)
        self.assertIn(PIPELINE_CONFIG, fp)
        self.assertTrue(any(path.endswith(".jsonl") for path in fp))

    def test_snapshot_ignores_non_jsonl_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            open(os.path.join(tmp, "a.jsonl"), "w", encoding="utf-8").close()
            open(os.path.join(tmp, "notes.txt"), "w", encoding="utf-8").close()
            fp = snapshot(PIPELINE_CONFIG, tmp)
            self.assertTrue(any(path.endswith("a.jsonl") for path in fp))
            self.assertFalse(any(path.endswith("notes.txt") for path in fp))

    def test_snapshot_tolerates_missing_config_and_input_dir(self):
        fp = snapshot("/no/such/config.json", "/no/such/dir")
        self.assertEqual(fp, {})

    def test_two_snapshots_of_unchanged_files_are_equal(self):
        first = snapshot(PIPELINE_CONFIG, INPUT_DIR)
        second = snapshot(PIPELINE_CONFIG, INPUT_DIR)
        self.assertEqual(first, second)

    def test_snapshot_changes_when_a_watched_file_is_modified(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = os.path.join(tmp, "pipeline.json")
            with open(config_path, "w", encoding="utf-8") as handle:
                handle.write("{}")
            before = snapshot(config_path, tmp)
            # Force a different (mtime, size) pair regardless of filesystem
            # timestamp resolution, which a wall-clock-based test would flake on.
            with open(config_path, "w", encoding="utf-8") as handle:
                handle.write("{}\n\n\n")
            os.utime(config_path, (before[config_path][0] + 5, before[config_path][0] + 5))
            after = snapshot(config_path, tmp)
            self.assertNotEqual(before, after)


class WatchDebounceTest(unittest.TestCase):
    """Drive watch() with a fake clock and canned snapshots so debounce
    behaviour is deterministic and does not depend on real elapsed time.
    """

    def _fake_watch(self, snapshots, *, debounce=1.0, poll_interval=0.1):
        calls = []
        fake_time = {"t": 0.0}
        remaining = list(snapshots)

        def fake_clock():
            return fake_time["t"]

        def fake_sleep(_seconds):
            fake_time["t"] += 1.0  # advance well past any debounce window per poll

        # Patch snapshot() as seen by the watcher module for this test only.
        import streamloom.watcher as watcher_module

        original_snapshot = watcher_module.snapshot

        def fake_snapshot(config_path, input_dir):
            if remaining:
                return remaining.pop(0)
            return remaining_last[0]

        remaining_last = [snapshots[-1] if snapshots else {}]
        watcher_module.snapshot = fake_snapshot
        try:
            run_count = watcher_module.watch(
                "cfg.json",
                "input/",
                lambda: calls.append(fake_time["t"]),
                poll_interval=poll_interval,
                debounce=debounce,
                max_iterations=len(snapshots),
                clock=fake_clock,
                sleep=fake_sleep,
            )
        finally:
            watcher_module.snapshot = original_snapshot
        return run_count, calls

    def test_initial_call_happens_immediately(self):
        run_count, calls = self._fake_watch([{"a": (1, 1)}] * 3)
        self.assertGreaterEqual(run_count, 1)
        self.assertEqual(calls[0], 0.0)

    def test_burst_of_changes_collapses_into_one_rerun(self):
        # Snapshot changes on the first three polls, then settles: this must
        # trigger exactly one debounced re-run, not three.
        snapshots = [
            {"a": (1, 1)},
            {"a": (2, 1)},
            {"a": (3, 1)},
            {"a": (3, 1)},
            {"a": (3, 1)},
        ]
        run_count, calls = self._fake_watch(snapshots, debounce=1.0, poll_interval=0.1)
        # 1 initial call + exactly 1 debounced re-run once the snapshot settles.
        self.assertEqual(run_count, 2)

    def test_no_change_never_triggers_a_rerun(self):
        snapshots = [{"a": (1, 1)}] * 4
        run_count, _calls = self._fake_watch(snapshots, debounce=1.0, poll_interval=0.1)
        self.assertEqual(run_count, 1)

    def test_max_iterations_bounds_the_loop(self):
        snapshots = [{"a": (i, 1)} for i in range(10)]
        run_count, _calls = self._fake_watch(snapshots, debounce=100.0, poll_interval=0.1)
        # debounce never elapses, so only the initial call happens.
        self.assertEqual(run_count, 1)


if __name__ == "__main__":
    unittest.main()
