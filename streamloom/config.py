"""Config schema for streamloom pipelines.

A pipeline config is a small JSON document describing an ordered list of
``map`` / ``filter`` / ``reduce`` stages to run over a stream of JSONL
records. Every stage is a fixed, named primitive with validated arguments --
there is no expression language and nothing in a config is ever passed to
``eval``/``exec``, so loading and running a config can never execute
arbitrary code from the file.

Example config::

    {
      "stages": [
        {"type": "filter", "conditions": [{"field": "level", "op": "eq", "value": "error"}]},
        {"type": "map", "select": ["message", "user"], "rename": {"message": "msg"}},
        {"type": "reduce", "op": "count", "as": "error_count"}
      ]
    }
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Tuple, Union

Record = Dict[str, Any]


class ConfigError(ValueError):
    """Raised when a pipeline config is malformed or fails validation."""


_FILTER_OPS = {"eq", "ne", "gt", "gte", "lt", "lte", "in", "contains", "exists", "not_exists"}
_NO_VALUE_OPS = {"exists", "not_exists"}
_REDUCE_OPS = {"count", "sum", "min", "max", "collect", "first", "last"}
_REDUCE_OPS_NEEDING_FIELD = {"sum", "min", "max", "collect", "first", "last"}


def _eval_condition(record: Record, condition: Dict[str, Any]) -> bool:
    field_name = condition["field"]
    op = condition["op"]
    present = field_name in record

    if op == "exists":
        return present
    if op == "not_exists":
        return not present
    if not present:
        return False

    value = record[field_name]
    target = condition["value"]

    try:
        if op == "eq":
            return value == target
        if op == "ne":
            return value != target
        if op == "gt":
            return value > target
        if op == "gte":
            return value >= target
        if op == "lt":
            return value < target
        if op == "lte":
            return value <= target
        if op == "in":
            return value in target
        if op == "contains":
            return target in value
    except TypeError:
        # Comparing incompatible types (e.g. a string field against a
        # numeric threshold) never matches rather than crashing the pipeline.
        return False

    raise ConfigError(f"unhandled filter op {op!r}")  # pragma: no cover - guarded by validation


@dataclass(frozen=True)
class FilterStage:
    """Keep only records that satisfy a set of conditions."""

    conditions: List[Dict[str, Any]]
    match: str = "all"

    def apply(self, records: Iterable[Record]) -> Iterator[Record]:
        combiner = all if self.match == "all" else any
        for record in records:
            if combiner(_eval_condition(record, cond) for cond in self.conditions):
                yield record


@dataclass(frozen=True)
class MapStage:
    """Transform each record into a new record."""

    select: Optional[List[str]] = None
    drop: List[str] = field(default_factory=list)
    rename: Dict[str, str] = field(default_factory=dict)
    set_fields: Dict[str, Any] = field(default_factory=dict)

    def apply(self, records: Iterable[Record]) -> Iterator[Record]:
        for record in records:
            if self.select is None:
                out = dict(record)
            else:
                out = {key: record[key] for key in self.select if key in record}
            for key in self.drop:
                out.pop(key, None)
            for old_key, new_key in self.rename.items():
                if old_key in out:
                    out[new_key] = out.pop(old_key)
            out.update(self.set_fields)
            yield out


@dataclass(frozen=True)
class ReduceStage:
    """Fold the current stream of records into a single record."""

    op: str
    source_field: Optional[str] = None
    as_field: str = "result"

    def apply(self, records: Iterable[Record]) -> Iterator[Record]:
        materialized = list(records)

        if self.op == "count":
            result: Any = len(materialized)
        elif self.op == "collect":
            result = [rec.get(self.source_field) for rec in materialized if self.source_field in rec]
        elif self.op == "first":
            result = materialized[0].get(self.source_field) if materialized else None
        elif self.op == "last":
            result = materialized[-1].get(self.source_field) if materialized else None
        elif self.op in ("sum", "min", "max"):
            values = [rec[self.source_field] for rec in materialized if self.source_field in rec]
            if not values:
                result = 0 if self.op == "sum" else None
            elif self.op == "sum":
                result = sum(values)
            elif self.op == "min":
                result = min(values)
            else:
                result = max(values)
        else:
            raise ConfigError(f"unhandled reduce op {self.op!r}")  # pragma: no cover

        yield {self.as_field: result}


Stage = Union[FilterStage, MapStage, ReduceStage]

_STAGE_TYPE_NAMES = {
    FilterStage: "filter",
    MapStage: "map",
    ReduceStage: "reduce",
}


def stage_type_name(stage: Stage) -> str:
    """Return the config `type` string (``"filter"``/``"map"``/``"reduce"``) for a stage."""
    try:
        return _STAGE_TYPE_NAMES[type(stage)]
    except KeyError:  # pragma: no cover - guarded by the closed Stage union
        raise ConfigError(f"unknown stage type {type(stage).__name__}") from None


@dataclass(frozen=True)
class StageTiming:
    """How long one stage of a pipeline run took, and how many records it saw."""

    index: int
    type: str
    input_count: int
    output_count: int
    elapsed_seconds: float


@dataclass(frozen=True)
class Pipeline:
    """An ordered list of stages to run over a stream of records."""

    stages: List[Stage]

    def run(self, records: Iterable[Record]) -> List[Record]:
        result, _timings = self.run_with_timings(records)
        return result

    def run_with_timings(
        self,
        records: Iterable[Record],
        *,
        clock: Callable[[], float] = time.perf_counter,
    ) -> Tuple[List[Record], List[StageTiming]]:
        """Run every stage in order, timing each one and counting its records.

        Each stage is materialized to a list before the next one starts, so
        the input/output counts and elapsed time reported for a stage are
        exactly that stage's -- with the lazy generator chaining
        :meth:`run` also uses internally, timing would smear across stage
        boundaries as each generator pulls from the one before it.
        """
        current: List[Record] = list(records)
        timings: List[StageTiming] = []
        for index, stage in enumerate(self.stages):
            input_count = len(current)
            start = clock()
            current = list(stage.apply(current))
            elapsed = clock() - start
            timings.append(
                StageTiming(
                    index=index,
                    type=stage_type_name(stage),
                    input_count=input_count,
                    output_count=len(current),
                    elapsed_seconds=elapsed,
                )
            )
        return current, timings


def _require_dict(value: Any, where: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigError(f"{where}: must be an object")
    return value


def _parse_filter(index: int, raw: Dict[str, Any]) -> FilterStage:
    where = f"stage {index} (filter)"
    conditions = raw.get("conditions")
    if not isinstance(conditions, list) or not conditions:
        raise ConfigError(f"{where}: 'conditions' must be a non-empty list")

    parsed: List[Dict[str, Any]] = []
    for j, raw_cond in enumerate(conditions):
        cond = _require_dict(raw_cond, f"{where}: condition {j}")
        cond_field = cond.get("field")
        op = cond.get("op")
        if not isinstance(cond_field, str) or not cond_field:
            raise ConfigError(f"{where}: condition {j}: 'field' must be a non-empty string")
        if op not in _FILTER_OPS:
            raise ConfigError(f"{where}: condition {j}: unknown op {op!r}")
        if op not in _NO_VALUE_OPS and "value" not in cond:
            raise ConfigError(f"{where}: condition {j}: op {op!r} requires 'value'")
        parsed.append({"field": cond_field, "op": op, "value": cond.get("value")})

    match = raw.get("match", "all")
    if match not in ("all", "any"):
        raise ConfigError(f"{where}: 'match' must be 'all' or 'any'")

    return FilterStage(conditions=parsed, match=match)


def _parse_map(index: int, raw: Dict[str, Any]) -> MapStage:
    where = f"stage {index} (map)"
    select = raw.get("select")
    drop = raw.get("drop", [])
    rename = raw.get("rename", {})
    set_fields = raw.get("set", {})

    if select is not None and (
        not isinstance(select, list) or not all(isinstance(x, str) for x in select)
    ):
        raise ConfigError(f"{where}: 'select' must be a list of strings")
    if not isinstance(drop, list) or not all(isinstance(x, str) for x in drop):
        raise ConfigError(f"{where}: 'drop' must be a list of strings")
    if not isinstance(rename, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in rename.items()
    ):
        raise ConfigError(f"{where}: 'rename' must be an object of string to string")
    if not isinstance(set_fields, dict):
        raise ConfigError(f"{where}: 'set' must be an object")
    if select is None and not drop and not rename and not set_fields:
        raise ConfigError(f"{where}: must specify at least one of select, drop, rename, set")

    return MapStage(select=select, drop=list(drop), rename=dict(rename), set_fields=dict(set_fields))


def _parse_reduce(index: int, raw: Dict[str, Any]) -> ReduceStage:
    where = f"stage {index} (reduce)"
    op = raw.get("op")
    if op not in _REDUCE_OPS:
        raise ConfigError(f"{where}: unknown op {op!r}")

    source_field = raw.get("field")
    if op in _REDUCE_OPS_NEEDING_FIELD:
        if not isinstance(source_field, str) or not source_field:
            raise ConfigError(f"{where}: op {op!r} requires a string 'field'")

    as_field = raw.get("as", op)
    if not isinstance(as_field, str) or not as_field:
        raise ConfigError(f"{where}: 'as' must be a non-empty string")

    return ReduceStage(op=op, source_field=source_field, as_field=as_field)


_PARSERS = {
    "filter": _parse_filter,
    "map": _parse_map,
    "reduce": _parse_reduce,
}


def _parse_stage(index: int, raw: Any) -> Stage:
    stage = _require_dict(raw, f"stage {index}")
    stage_type = stage.get("type")
    parser = _PARSERS.get(stage_type)
    if parser is None:
        raise ConfigError(
            f"stage {index}: unknown type {stage_type!r} (expected map, filter, or reduce)"
        )
    return parser(index, stage)


def parse_config(data: Dict[str, Any]) -> Pipeline:
    """Validate a decoded config document and build a :class:`Pipeline`."""
    top = _require_dict(data, "config")
    raw_stages = top.get("stages")
    if not isinstance(raw_stages, list) or not raw_stages:
        raise ConfigError("config must define a non-empty 'stages' list")

    stages = [_parse_stage(i, raw) for i, raw in enumerate(raw_stages)]
    return Pipeline(stages=stages)


def load_config(path: str) -> Pipeline:
    """Read and parse a pipeline config from a JSON file on disk."""
    with open(path, "r", encoding="utf-8") as handle:
        try:
            data = json.load(handle)
        except json.JSONDecodeError as exc:
            raise ConfigError(f"{path}: invalid JSON ({exc})") from exc
    try:
        return parse_config(data)
    except ConfigError as exc:
        raise ConfigError(f"{path}: {exc}") from exc
