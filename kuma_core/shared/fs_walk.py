"""One recursive directory walk that answers several ``rglob`` patterns at once.

``sorted(d.rglob("*.fastq")) + sorted(d.rglob("*.fastq.gz"))`` is two complete
recursive walks of the same tree for two mutually exclusive patterns.  On a
local filesystem that is cheap; on a Windows share (9p/drvfs) it is not, because
``readdir`` there often returns ``DT_UNKNOWN``, which forces ``pathlib`` to
``lstat`` every child just to decide whether to recurse into it.  The tree is
therefore stat-ed once per pattern rather than once in total.

:func:`rglob_entries` walks the tree a single time and buckets the matches by
pattern, so the caller can rebuild the exact list it had before.  It also hands
back the ``os.DirEntry`` for every match: ``DirEntry.stat()`` reuses the
``lstat`` the walk already paid for when the entry is not a symlink, which
removes a second metadata round-trip for callers that only want ``st_size``.

Matching semantics are ``Path.rglob``, not shell glob, reproduced deliberately:

* patterns are compiled with :func:`fnmatch.translate`, and ``re.IGNORECASE`` is
  applied on Windows only, exactly as ``pathlib`` does for its flavour;
* a leading dot is not special, so ``*.fastq`` matches ``.hidden.fastq`` here
  just as it does under ``Path.rglob``;
* the pattern is matched against every entry regardless of type, so a
  *directory* named ``x.fastq`` is returned, as ``rglob`` returns it;
* recursion skips symlinked directories, so a symlink loop cannot hang the walk
  and a linked tree is not visited twice;
* ``PermissionError`` on a subdirectory prunes that branch instead of aborting.

``kuma_core.mame.ingest.stage_marker`` applies the same ``fnmatch.translate``
technique to a single non-recursive directory; this module is the recursive,
multi-pattern counterpart.
"""

from __future__ import annotations

import fnmatch
import os
import re
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path

# ``pathlib`` compiles glob patterns case-insensitively on Windows flavours only.
_GLOB_FLAGS = re.IGNORECASE if os.name == "nt" else 0

# ``(path, entry)`` for one match; the entry carries the walk's cached lstat.
MatchList = list[tuple[Path, "os.DirEntry[str]"]]


@lru_cache(maxsize=64)
def _compile(pattern: str) -> re.Pattern[str]:
    return re.compile(fnmatch.translate(pattern), _GLOB_FLAGS)


def rglob_entries(root: Path, patterns: Sequence[str]) -> dict[str, MatchList]:
    """Return ``{pattern: [(path, entry), ...]}`` from a single walk of *root*.

    Every pattern gets its own bucket, and a name matching two patterns lands in
    both, so the result is what the equivalent sequence of ``root.rglob(p)``
    calls would have produced pattern by pattern.

    Order within a bucket is directory-walk order, which ``Path.rglob`` also
    leaves unspecified; callers that relied on ``sorted(...)`` must keep sorting.

    A *root* that cannot be scanned (missing, not a directory, unreadable)
    yields empty buckets rather than raising, so a caller that already checked
    ``is_dir()`` sees no behaviour change and one that did not gets the empty
    result it would have got from a ``glob`` over the same path.
    """
    matchers = [(pattern, _compile(pattern)) for pattern in patterns]
    out: dict[str, MatchList] = {pattern: [] for pattern, _ in matchers}

    stack = [Path(root)]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                entries = list(it)
        except OSError:
            # Missing / unreadable directory: prune this branch, keep walking.
            continue
        for entry in entries:
            name = entry.name
            for pattern, matcher in matchers:
                if matcher.match(name):
                    out[pattern].append((current / name, entry))
            try:
                descend = entry.is_dir() and not entry.is_symlink()
            except OSError:
                descend = False
            if descend:
                stack.append(current / name)

    return out


def rglob_paths(root: Path, patterns: Sequence[str]) -> dict[str, list[Path]]:
    """:func:`rglob_entries` without the ``DirEntry``, for size-agnostic callers."""
    return {
        pattern: [path for path, _entry in matches]
        for pattern, matches in rglob_entries(root, patterns).items()
    }


__all__ = ["MatchList", "rglob_entries", "rglob_paths"]
