"""Debounced polling watcher for a pipeline config and its input directory.

There is no dependency on OS-level filesystem-event APIs (inotify, FSEvents,
ReadDirectoryChangesW) -- those differ per platform and would pull in a
third-party binding, so this watches by polling ``os.stat`` on the config
file and every ``*.jsonl`` file in the input directory, comparing successive
snapshots.

A raw "re-run on every change" loop is unusable in practice: an editor saving
a config file can produce several write events in a few milliseconds, and a
producer appending records to a JSONL file line-by-line would otherwise
trigger a run per line. :func:`watch` instead waits for a *quiescent* period
(``debounce`` seconds with no further change) before calling ``on_change``,
so a burst of edits collapses into a single re-run once things settle.
"""

from __future__ import annotations

import os
import time
from typing import Callable, Dict, List, Optional, Tuple

from .executor import discover_input_files

Fingerprint = Dict[str, Tuple[float, int]]


def _stat_fingerprint(path: str) -> Optional[Tuple[float, int]]:
    """Return ``(mtime, size)`` for ``path``, or ``None`` if it cannot be stat'd."""
    try:
        stat_result = os.stat(path)
    except OSError:
        return None
    return (stat_result.st_mtime, stat_result.st_size)


def snapshot(config_path: str, input_dir: str) -> Fingerprint:
    """Fingerprint the config file and every ``*.jsonl`` file in ``input_dir``.

    Missing files (a config not yet written, an input directory not yet
    created) are simply absent from the result rather than raising -- a
    watcher has to tolerate the thing it watches not existing yet, since
    that is the normal state before the first edit.

    Two snapshots compare equal exactly when nothing watched has been added,
    removed, or modified between them, which is the condition :func:`watch`
    uses to detect a change.
    """
    paths: List[str] = [config_path]
    if os.path.isdir(input_dir):
        paths.extend(discover_input_files(input_dir))

    fingerprint: Fingerprint = {}
    for path in paths:
        stat = _stat_fingerprint(path)
        if stat is not None:
            fingerprint[path] = stat
    return fingerprint


def watch(
    config_path: str,
    input_dir: str,
    on_change: Callable[[], None],
    *,
    poll_interval: float = 0.5,
    debounce: float = 1.0,
    max_iterations: Optional[int] = None,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Poll ``config_path`` and ``input_dir`` for changes, debouncing re-runs.

    ``on_change`` is called once immediately (the initial run), then again
    each time a change is detected and the watched files then stay
    unchanged for ``debounce`` seconds -- so a burst of several rapid edits
    triggers exactly one re-run, after it settles.

    ``max_iterations`` bounds the number of poll cycles (``None`` means run
    until ``KeyboardInterrupt``); it exists so this function is unit
    testable without an unbounded real-time loop. ``clock`` and ``sleep``
    are injectable for the same reason.

    Returns the number of times ``on_change`` was invoked, including the
    initial call.
    """
    on_change()
    run_count = 1

    last_snapshot = snapshot(config_path, input_dir)
    pending_since: Optional[float] = None

    iterations = 0
    while max_iterations is None or iterations < max_iterations:
        iterations += 1
        sleep(poll_interval)

        current_snapshot = snapshot(config_path, input_dir)
        if current_snapshot != last_snapshot:
            last_snapshot = current_snapshot
            pending_since = clock()
        elif pending_since is not None and clock() - pending_since >= debounce:
            on_change()
            run_count += 1
            pending_since = None

    return run_count
