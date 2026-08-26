# streamloom

A zero-dependency Python daemon that watches a directory of append-only
JSONL files and runs each new record through a declarative map/filter/reduce
pipeline defined in a small JSON config file. The config hot-reloads when it
changes, and every run writes a structural diff against the previous output
so the effect of an edit is visible immediately.

This is an early milestone: the pipeline config schema, and a deterministic
executor that runs a config once over a directory of JSONL fixtures. The
directory watcher, hot-reload loop, and diff output described above are not
built yet.

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
keys are sorted and indentation is fixed -- since a later milestone diffs
each run's output against the previous one.

The same thing is available from the command line:

```
python -m streamloom run pipeline.json events/ output.json
```

This runs the pipeline once and exits; it does not yet watch the directory
for new files.

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
