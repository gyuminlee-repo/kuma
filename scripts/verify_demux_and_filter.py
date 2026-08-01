# ruff: noqa: T201
"""Output-identity and syscall harness for the ``demux_and_filter`` handler.

``scripts/perf_step2_harness.py`` drives ``run_combinatorial_demux``; it never
enters ``sidecar_mame.handlers.demux.handle_demux_and_filter``, which is the
handler the frontend calls from ``inputSlice`` for the custom-barcode demux
path.  An optimization to that handler therefore cannot be validated by the
step 2 harness, and this script covers exactly that gap.

It builds a deterministic multi-NB fixture, calls the handler once, and prints a
fingerprint carrying:

* ``tree_sha256`` over every output file (relative path and content), plus the
  JSON-RPC response with its key order preserved, so a change to the response
  dict ordering is caught as well as a change to the bytes on disk;
* metadata-syscall and fsync counts observed at the ``os`` boundary (strace is
  not available on this host), which are load independent and therefore usable
  while other benchmarks run concurrently;
* wall seconds, reported for information only.

Run it once on the baseline commit and once on the change, then diff the two
fingerprints::

    .venv/bin/python scripts/verify_demux_and_filter.py --json /tmp/after.json

The fixture is synthetic on purpose: a real MinKNOW run is not committed, and
the identity claim needs a workload that is byte-reproducible across checkouts.
Reads are ``<barcode> + <reference>`` so demux assigns them and minimap2 aligns
them full span; ``--wells`` and ``--files-per-nb`` scale the file count, which
is what the walk and fsync costs are proportional to.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent
# Resolve both layers from the checkout that owns THIS script, not from the
# current directory or an editable install: the before/after comparison runs the
# same script against two different checkouts, and picking up kuma_core from the
# wrong one would silently compare a tree against itself.
sys.path.insert(0, str(_REPO / "python-core"))
sys.path.insert(0, str(_REPO))

_REFERENCE = (
    "ATGGTGTTCAAGAACTTCGATGCGCTGACCGGCAAAGACCTGAAAGAGTTCGCGAAATCG"
    "AACGGCATGAACCTGAACAAGCTGAAAGCGTTCAACCAGTTCGCGAACATGAAAGCGTTC"
    "AACAAGTACTTCAACAAGATCTTCAACAAGTTCGCGAACATGAACAAGTTCAACTGA"
)

_ALPHABET = "ACGT"


def _barcode_for(index: int) -> str:
    """A deterministic distinct 10-mer for well *index* (base-4 over ACGT)."""
    digits = []
    n = index
    for _ in range(5):
        digits.append(_ALPHABET[n % 4])
        n //= 4
    # A constant 5-mer suffix keeps every barcode the same length and keeps the
    # variable part at the 5' end where the demux prefix scan looks.
    return "".join(reversed(digits)) + "ACGTA"


def build_fixture(
    root: Path, n_wells: int, n_nb: int, files_per_nb: int, reads_per_well: int
) -> dict[str, Any]:
    """Write a deterministic MinKNOW-shaped fixture; return the handler params."""
    barcodes = {f"W{i:03d}": _barcode_for(i) for i in range(n_wells)}

    fastq_pass = root / "fastq_pass"
    summary_rows: list[str] = []
    for nb in range(1, n_nb + 1):
        nb_dir = fastq_pass / f"barcode{nb:02d}"
        nb_dir.mkdir(parents=True)
        # Spread the wells across files the way MinKNOW splits every 4000 reads.
        records: list[tuple[str, str]] = []
        for well, bc in barcodes.items():
            for r in range(reads_per_well):
                read_id = f"nb{nb}_{well}_{r}"
                records.append((read_id, bc + _REFERENCE))
                # Fail every 7th read on qscore so the quality filter actually
                # rewrites files rather than copying them unchanged.
                qscore = 3.0 if (r % 7 == 0) else 20.0
                summary_rows.append(
                    f"{read_id}\t{len(bc) + len(_REFERENCE)}\t{qscore}\t90.0"
                )
        per_file = max(1, len(records) // files_per_nb + 1)
        for fi in range(files_per_nb):
            chunk = records[fi * per_file : (fi + 1) * per_file]
            path = nb_dir / f"reads_{fi}.fastq.gz"
            with gzip.open(path, "wt", encoding="utf-8", compresslevel=1) as fh:
                for read_id, seq in chunk:
                    fh.write(f"@{read_id}\n{seq}\n+\n{'I' * len(seq)}\n")
            # mtime is not hashed, but pin it anyway so nothing downstream can
            # accidentally make the fingerprint time dependent.
            os.utime(path, (1700000000, 1700000000))

    summary = root / "sequencing_summary.txt"
    summary.write_text(
        "read_id\tsequence_length_template\tmean_qscore_template\tbarcode_score\n"
        + "\n".join(summary_rows)
        + "\n",
        encoding="utf-8",
    )

    ref = root / "reference.fasta"
    ref.write_text(f">ref\n{_REFERENCE}\n", encoding="utf-8")

    return {
        "fastq_dir": str(fastq_pass),
        "custom_barcodes": barcodes,
        "output_dir": str(root / "out"),
        "reference_fasta": str(ref),
        "sequencing_summary": str(summary),
        "use_cutadapt": False,
        "auto_detect_length": False,
        "min_qscore": 8.0,
        "length_min": 0,
        "length_max": 100000,
        "min_barcode_score": 0.0,
    }


def _sha256_tree(root: Path) -> tuple[str, int]:
    h = hashlib.sha256()
    files = sorted(p for p in root.rglob("*") if p.is_file())
    for path in files:
        h.update(path.relative_to(root).as_posix().encode("utf-8"))
        h.update(b"\0")
        h.update(path.read_bytes())
        h.update(b"\0")
    return h.hexdigest(), len(files)


class _Counter:
    """Count metadata operations at the ``os`` boundary.

    ``os.DirEntry.stat`` is implemented in C and cannot be patched, so entries
    handed back by a patched ``os.scandir`` are wrapped in a proxy that counts
    it.  Without the proxy the comparison would silently flatter the scandir
    version by hiding exactly the calls it added.
    """

    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self._orig: dict[str, Any] = {}

    def _bump(self, key: str) -> None:
        self.counts[key] = self.counts.get(key, 0) + 1

    def __enter__(self) -> "_Counter":
        counter = self

        class _EntryProxy:
            __slots__ = ("_e",)

            def __init__(self, e: Any) -> None:
                self._e = e

            @property
            def name(self) -> str:
                return self._e.name

            @property
            def path(self) -> str:
                return self._e.path

            def stat(self, *a: Any, **kw: Any) -> Any:
                counter._bump("direntry_stat")
                return self._e.stat(*a, **kw)

            def is_dir(self, *a: Any, **kw: Any) -> bool:
                counter._bump("direntry_is_dir")
                return self._e.is_dir(*a, **kw)

            def is_file(self, *a: Any, **kw: Any) -> bool:
                counter._bump("direntry_is_file")
                return self._e.is_file(*a, **kw)

            def is_symlink(self, *a: Any, **kw: Any) -> bool:
                counter._bump("direntry_is_symlink")
                return self._e.is_symlink(*a, **kw)

            def inode(self) -> int:
                return self._e.inode()

        class _ScandirProxy:
            def __init__(self, it: Any) -> None:
                self._it = it

            def __iter__(self) -> Any:
                for e in self._it:
                    yield _EntryProxy(e)

            def __enter__(self) -> "_ScandirProxy":
                return self

            def __exit__(self, *exc: Any) -> None:
                self._it.close()

            def close(self) -> None:
                self._it.close()

        for name in ("stat", "lstat", "fsync", "listdir", "open", "replace", "unlink"):
            self._orig[name] = getattr(os, name)

        def wrap(name: str) -> Any:
            orig = self._orig[name]

            def inner(*a: Any, **kw: Any) -> Any:
                self._bump(name)
                return orig(*a, **kw)

            return inner

        for name in self._orig:
            setattr(os, name, wrap(name))

        self._orig["scandir"] = os.scandir

        def scandir(*a: Any, **kw: Any) -> Any:
            self._bump("scandir")
            return _ScandirProxy(self._orig["scandir"](*a, **kw))

        os.scandir = scandir  # type: ignore[assignment]
        return self

    def __exit__(self, *exc: Any) -> None:
        for name, orig in self._orig.items():
            setattr(os, name, orig)

    def summary(self) -> dict[str, int]:
        walk = self.counts.get("scandir", 0) + self.counts.get("listdir", 0)
        stats = (
            self.counts.get("stat", 0)
            + self.counts.get("lstat", 0)
            + self.counts.get("direntry_stat", 0)
            + self.counts.get("direntry_is_dir", 0)
            + self.counts.get("direntry_is_file", 0)
            + self.counts.get("direntry_is_symlink", 0)
        )
        out = dict(sorted(self.counts.items()))
        out["TOTAL_dir_scans"] = walk
        out["TOTAL_metadata"] = stats
        return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--wells", type=int, default=96)
    ap.add_argument("--nb", type=int, default=3)
    ap.add_argument("--files-per-nb", type=int, default=8)
    ap.add_argument("--reads-per-well", type=int, default=7)
    ap.add_argument("--minimap2", default=None)
    ap.add_argument("--out-root", default=None, help="where the fixture is built")
    ap.add_argument("--json", default=None, help="write the fingerprint here")
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    mm2 = (
        args.minimap2
        or os.environ.get("KURO_MINIMAP2")
        or str(_REPO / "python-core/vendor/minimap2/linux-x64/minimap2")
    )
    if not Path(mm2).exists():
        print(f"ERROR: minimap2 not found at {mm2}; set KURO_MINIMAP2.", file=sys.stderr)
        return 2
    os.environ["KURO_MINIMAP2"] = str(Path(mm2).resolve())

    root = Path(
        args.out_root
        or tempfile.mkdtemp(prefix="kuma-demux-verify-", dir=os.environ.get("TMPDIR", "/tmp"))
    )
    if root.exists() and args.out_root:
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)

    try:
        params = build_fixture(
            root, args.wells, args.nb, args.files_per_nb, args.reads_per_well
        )

        from sidecar_mame.handlers.demux import handle_demux_and_filter

        counter = _Counter()
        t0 = time.perf_counter()
        with counter:
            response = handle_demux_and_filter(params)
        wall = time.perf_counter() - t0

        out_dir = Path(params["output_dir"])
        tree_hash, n_files = _sha256_tree(out_dir)

        # output_dir is an absolute temp path; drop it from the identity payload
        # so two checkouts running in different temp dirs stay comparable.
        response_for_hash = {k: v for k, v in response.items() if k != "output_dir"}
        response_blob = json.dumps(response_for_hash, ensure_ascii=False)
        fingerprint = {
            "identity": {
                "tree_sha256": tree_hash,
                "file_count": n_files,
                "response_sha256": hashlib.sha256(
                    response_blob.encode("utf-8")
                ).hexdigest(),
                "n_input_reads": response["n_input_reads"],
                "n_assigned": response["n_assigned"],
                "n_unassigned": response["n_unassigned"],
                "n_wells": len(response["per_well_counts"]),
                "filter_stats": response["filter_stats"],
            },
            "syscalls": counter.summary(),
            "timing": {"wall_s": round(wall, 4)},
            "fixture": {
                "wells": args.wells,
                "nb": args.nb,
                "files_per_nb": args.files_per_nb,
                "reads_per_well": args.reads_per_well,
            },
        }
        blob = json.dumps(fingerprint, indent=2, ensure_ascii=False)
        print(blob)
        if args.json:
            Path(args.json).write_text(blob + "\n", encoding="utf-8")
        return 0
    finally:
        if not args.keep and not args.out_root:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
