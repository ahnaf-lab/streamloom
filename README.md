# streamloom

A zero-dependency Python daemon that watches a directory of append-only
JSONL files and runs each new record through a declarative map/filter/reduce
pipeline defined in a small JSON config file. The config hot-reloads when it
changes, and every run writes a structural diff against the previous output
so the effect of an edit is visible immediately.

This is an early milestone: the pipeline config schema, a deterministic
executor that runs a config once over a directory of JSONL fixtures, a
debounced watcher that re-runs the pipeline when the config or input
directory changes, and a structural diff report written alongside each run's
output.

## Install

Requires Python 3.9 or later. There are no third-party dependencies -- the
whole project is built on the standard library, so a good pipeline runner
does not need any.

```
git clone <this-repo>
cd streamloom
```

Nothing to install; import the `streamloom` package directly from the
repository root.

## Usage

Pipelines are described as JSON: an ordered list of `map`, `filter`, and
`reduce` stages. There is no expression language -- every stage is a fixed,
named operation with validated arguments, so a config file can never run
arbitrary code.

```python
from streamloom import parse_config

config = {
    "stages": [
        {"type": "filter", "conditions": [{"field": "level", "op": "eq", "value": "error"}]},
        {"type": "map", "select": ["message", "user"], "rename": {"message": "msg"}},
        {"type": "reduce", "op": "count", "as": "error_count"},
    ]
}

pipeline = parse_config(config)
records = [
    {"level": "error", "message": "boom", "user": "a"},
    {"level": "info", "message": "ok", "user": "b"},
]
pipeline.run(records)  # -> [{"error_count": 1}]
```

Load a pipeline from a file on disk instead of an in-memory dict:

```python
from streamloom import load_config

pipeline = load_config("pipeline.json")
```

Read records straight out of a JSONL file:

```python
from streamloom import read_jsonl

records = list(read_jsonl("events.jsonl"))
```

### Running a pipeline over a directory

`execute` reads every `*.jsonl` file in a directory (concatenated in sorted
filename order, so the result never depends on filesystem listing order),
runs the pipeline once, and writes the result as a formatted JSON array:

```python
from streamloom import execute

result = execute("pipeline.json", "events/", "output.json")
```

The same config and input directory always produce byte-identical output --
keys are sorted and indentation is fixed -- since each run diffs its output
against the previous one, and a diff is only meaningful if unrelated
formatting noise can never appear in it.

The same thing is available from the command line:

```
python -m streamloom run pipeline.json events/ output.json
```

This runs the pipeline once and exits.

### Diffing against the previous run

Every `execute` call reads whatever is already at the output path *before*
overwriting it, diffs the decoded JSON of the old and new results, and
writes a plain-text report to `<output path>.diff`:

```
$ python -m streamloom run pipeline.json events/ output.json
wrote 1 record(s) to output.json
$ cat output.json.diff
no previous output -- this is the initial run
$ echo '{"level": "error", "service": "billing"}' >> events/more.jsonl
$ python -m streamloom run pipeline.json events/ output.json
wrote 1 record(s) to output.json
$ cat output.json.diff
+ $[0].services_with_errors[1] = "billing"
```

The diff is structural, not textual: it walks the decoded JSON values
(dicts key by key, lists index by index) rather than comparing formatted
text, so reordering that changes nothing never shows up as a change. Each
line is one of:

- `+ path = value` -- added
- `- path = value` -- removed
- `~ path: old -> new` -- changed

If nothing changed since the previous run, the report reads `no change`.
If there is no previous output to compare against (the first run, or a file
that was not valid JSON), it reads `no previous output -- this is the
initial run` instead of listing every field as newly added.

```python
from streamloom import diff_values, format_diff

entries = diff_values({"count": 1}, {"count": 2})
format_diff(entries, is_initial=False)  # -> "~ $.count: 1 -> 2\n"
```

### Watching for changes

`watch` re-runs the pipeline whenever the config file or any `*.jsonl` file
in the input directory changes. There is no dependency on an OS-level
filesystem-event API (inotify, FSEvents, and so on differ per platform and
would each pull in a third-party binding); instead it polls file
modification time and size at a fixed interval.

A raw "re-run on every change" loop is unusable in practice -- an editor can
produce several write events for one save, and a producer appending records
line-by-line would otherwise trigger a run per line. `watch` waits for a
debounce period of no further change before re-running, so a burst of edits
collapses into a single re-run once things settle:

```python
from streamloom import watch

def on_change():
    print("input or config changed, re-running")

watch("pipeline.json", "events/", on_change, poll_interval=0.5, debounce=1.0)
```

From the command line:

```
python -m streamloom watch pipeline.json events/ output.json --interval 0.5 --debounce 1.0
```

This runs the pipeline once immediately, then keeps watching and re-running
until interrupted with Ctrl-C. `--interval` controls how often the watcher
polls (in seconds); `--debounce` controls how long the watched files must
stay unchanged before a re-run fires.

### Stage reference

- **filter** -- keep records matching a list of `conditions` (`field`, `op`,
  optional `value`). `op` is one of `eq`, `ne`, `gt`, `gte`, `lt`, `lte`,
  `in`, `contains`, `exists`, `not_exists`. `match` is `"all"` (default) or
  `"any"`.
- **map** -- reshape each record via any combination of `select` (keep only
  these fields), `drop` (remove fields), `rename` (old key to new key), and
  `set` (add literal constant fields).
- **reduce** -- fold the current stream into a single record. `op` is one of
  `count`, `sum`, `min`, `max`, `collect`, `first`, `last`. `field` names the
  source field for anything but `count`; `as` names the output key.

Invalid configs raise `streamloom.ConfigError` with a message naming the
offending stage index.

## Status

Built autonomously and gated on passing tests: every change here only ships
after the automated test suite runs clean.
