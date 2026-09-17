"""Temporary exact-preimage patcher for PR #425; removed before merge."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise RuntimeError(f"Preimage mismatch in {path}: {text.count(old)} occurrences")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


replace("kuma_core/kuro/mutation.py",
    "    return m.group(1), int(m.group(2)), m.group(3)\n",
    "    position = int(m.group(2))\n"
    "    if position < 1:\n"
    "        raise ValueError(\n"
    "            f\"Invalid mutation notation: '{notation}'. Amino acid positions are 1-based.\"\n"
    "        )\n"
    "    return m.group(1), position, m.group(3)\n")
replace("kuma_core/kuro/mutation.py",
    '    Only tokens matching the single-mutation regex are returned; "WT" and\n    other non-mutation tokens are silently dropped.\n',
    '    Explicit "WT" and empty separators carry no substitutions. Every other\n    token must be a valid, 1-based mutation; a malformed component rejects the\n    whole row rather than silently changing the requested genotype.\n')
replace("kuma_core/kuro/mutation.py",
    '        if _MUTATION_RE.match(token):\n            result.append(token)\n        # Silently skip "WT", empty strings, or other non-mutation tokens\n',
    '        if not token or token == "WT":\n            continue\n        parse_mutation_notation(token)\n        result.append(token)\n')

replace("kuma_core/mame/ingest/align.py", "import tempfile\n", "import tempfile\nimport threading\n")
replace("kuma_core/mame/ingest/align.py", "from kuma_core.mame.perf import TIMER\n",
    "from kuma_core.mame.perf import TIMER\nfrom kuma_core.mame.reference_fasta import multi_record_reason\n")
replace("kuma_core/mame/ingest/align.py",
    "    for match in _CIGAR_TOKEN_RE.finditer(cigar_str):\n        ops.append([int(match.group(1)), _CIGAR_LETTER_TO_OP[match.group(2)]])\n",
    "    for match in _CIGAR_TOKEN_RE.finditer(cigar_str):\n"
    "        if match.start() != pos:\n"
    "            raise ValueError(f\"Malformed CIGAR string: {cigar_str!r}\")\n"
    "        ops.append([int(match.group(1)), _CIGAR_LETTER_TO_OP[match.group(2)]])\n")
replace("kuma_core/mame/ingest/align.py", '''    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        shell=False,
    )
    if proc.stdout is None:
        raise RuntimeError("minimap2 stdout pipe unavailable")
    wall_key = f"{timing_prefix}.minimap2_wall"
    parse_key = f"{timing_prefix}.sam_parse"
    records: list[tuple[int, int, int, int, str]] = []
    while True:
        t0 = time.perf_counter()
        block = proc.stdout.readlines(_SAM_BLOCK_BYTES)
        TIMER.add(wall_key, time.perf_counter() - t0)
        if not block:
            break
        t1 = time.perf_counter()
        records.extend(_iter_sam_records_stream(block))
        TIMER.add(parse_key, time.perf_counter() - t1)
    _, err = proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(
            f"minimap2 failed (exit {proc.returncode}): "
            f"{(err or '').strip()[:500]}"
        )
    return records
''', '''    with subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
    ) as proc:
        stdout, stderr = proc.stdout, proc.stderr
        if stdout is None or stderr is None:
            proc.kill()
            raise RuntimeError("minimap2 output pipes unavailable")

        # Drain stderr concurrently: reading stdout to EOF first can deadlock
        # when the child fills stderr's OS pipe buffer. Keep diagnostics bounded
        # while consuming the entire stream; do not materialise SAM on disk.
        error_parts: list[str] = []

        def drain_stderr() -> None:
            retained = 0
            for chunk in iter(lambda: stderr.read(8192), ""):
                if retained < 500:
                    part = chunk[:500 - retained]
                    error_parts.append(part)
                    retained += len(part)

        error_reader = threading.Thread(
            target=drain_stderr, name="minimap2-stderr", daemon=True
        )
        error_reader.start()
        wall_key = f"{timing_prefix}.minimap2_wall"
        parse_key = f"{timing_prefix}.sam_parse"
        records: list[tuple[int, int, int, int, str]] = []
        try:
            while True:
                t0 = time.perf_counter()
                block = stdout.readlines(_SAM_BLOCK_BYTES)
                TIMER.add(wall_key, time.perf_counter() - t0)
                if not block:
                    break
                t1 = time.perf_counter()
                records.extend(_iter_sam_records_stream(block))
                TIMER.add(parse_key, time.perf_counter() - t1)
            proc.wait()
        except BaseException:
            # A parser failure or cancellation must not orphan a child blocked
            # writing the stream the caller has stopped reading.
            if proc.poll() is None:
                proc.kill()
            proc.wait()
            raise
        finally:
            error_reader.join()
        if proc.returncode != 0:
            raise RuntimeError(
                f"minimap2 failed (exit {proc.returncode}): "
                f"{''.join(error_parts).strip()}"
            )
        return records
''')
replace("kuma_core/mame/ingest/align.py", '''def _get_reference_length(reference_fasta: Path) -> int:
    """Return the total length of the first sequence in a FASTA file."""
    length = 0
    in_seq = False
    with reference_fasta.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\\r\\n")
            if line.startswith(">"):
                if in_seq:
                    # Second header found -- stop; use length of first sequence.
                    break
                in_seq = True
            elif in_seq:
                length += len(line.strip())
    if length == 0:
        raise ValueError(f"Reference FASTA contains no sequence data: {reference_fasta}")
    return length
''', '''def _get_reference_length(reference_fasta: Path) -> int:
    """Return the single reference length, rejecting multi-molecule input.

    Every alignment is checked against this length. Taking only the first
    record while minimap2 indexes every record would validate other molecules
    against the wrong coordinates.
    """
    lines = reference_fasta.read_text(encoding="utf-8").splitlines()
    reason = multi_record_reason(lines)
    if reason is not None:
        raise ValueError(reason)
    length = 0
    in_seq = False
    for line in lines:
        if line.startswith(">"):
            in_seq = True
        elif in_seq:
            length += len(line.strip())
    if length == 0:
        raise ValueError(f"Reference FASTA contains no sequence data: {reference_fasta}")
    return length
''')

replace("kuma_core/mame/ingest/stage_marker.py", "import re\n", "import re\nimport stat\n")
replace("kuma_core/mame/ingest/stage_marker.py", "def validate_marker(\n", '''def _marker_shape_error(marker: dict[str, Any], unit_dir: Path) -> str:
    """Validate persisted metadata before resume/consume interprets its values.

    Keep malformed objects distinguishable from absent legacy markers: resume
    recomputes them, while a consumer with a present marker fails closed.
    Versions 1 and 2 have the same inventory fields; v1 lacks input identity.
    """
    version = marker.get("schema_version")
    if type(version) is not int or version not in (1, MARKER_SCHEMA_VERSION):
        return "unsupported completion marker schema"
    if marker.get("stage") != STAGE_NAME:
        return "completion marker has an unexpected stage"
    if marker.get("unit") != Path(unit_dir).name:
        return "completion marker belongs to a different unit"
    if type(marker.get("consensus")) is not bool:
        return "completion marker consensus flag must be boolean"
    wells = marker.get("wells")
    if not isinstance(wells, list) or any(
        not isinstance(well, str) or not well.strip()
        or "/" in well or "\\\\" in well for well in wells
    ):
        return "completion marker wells must be a list of well names"
    if len(set(wells)) != len(wells):
        return "completion marker contains duplicate wells"
    counts = marker.get("per_well_counts")
    if not isinstance(counts, dict) or set(counts) != set(wells):
        return "completion marker read counts do not match its wells"
    if any(type(count) is not int or count < 0 for count in counts.values()):
        return "completion marker read counts must be non-negative integers"
    for key in ("n_input_reads", "n_unassigned"):
        value = marker.get(key)
        if value is not None and (type(value) is not int or value < 0):
            return f"completion marker {key} must be a non-negative integer"
    stats = marker.get("stats")
    if stats is not None and (
        not isinstance(stats, dict) or any(
            not isinstance(key, str) or type(value) is not int or value < 0
            for key, value in stats.items()
        )
    ):
        return "completion marker stats must contain non-negative integer counts"
    return ""


def validate_marker(
''')
replace("kuma_core/mame/ingest/stage_marker.py",
    '    if entries is None:\n        entries = scan_unit_dir(unit_dir)\n    recorded = {str(w) for w in marker.get("wells", [])}\n',
    '    shape_error = _marker_shape_error(marker, unit_dir)\n    if shape_error:\n        return (False, shape_error)\n    if entries is None:\n        entries = scan_unit_dir(unit_dir)\n    recorded = {str(w) for w in marker.get("wells", [])}\n')
replace("kuma_core/mame/ingest/stage_marker.py", "            size = entry.stat().st_size\n",
    "            info = entry.stat()\n"
    "            if not stat.S_ISREG(info.st_mode):\n"
    "                return (False, f\"recorded well '{well}' FASTA is not a regular file\")\n"
    "            size = info.st_size\n")

path = ROOT / "kuma_core/mame/export/janus_mapping.py"
if "import math\n" not in path.read_text(encoding="utf-8"):
    replace("kuma_core/mame/export/janus_mapping.py", "import csv\n", "import csv\nimport math\n")
replace("kuma_core/mame/export/janus_mapping.py",
    "        if self.output_schema == SCHEMA_DEVICE and not self.volume > 0:\n",
    "        if self.output_schema == SCHEMA_DEVICE and (\n"
    "            not math.isfinite(self.volume) or self.volume <= 0\n"
    "        ):\n")
replace("kuma_core/mame/export/janus_mapping.py",
    'f"Invalid volume {self.volume!r}. Expected a positive number of µL."',
    'f"Invalid volume {self.volume!r}. Expected a finite positive number of µL."')

for values, fallback in (("tmFwds", "tmFwd"), ("tmRevs", "tmRev"), ("tmOvs", "tmOverlap")):
    replace("src/lib/primerSuggestion.ts",
        f"    {fallback}: roundTo(median({values}), 1),\n",
        f"    {fallback}: roundTo({values}.length > 0 ? median({values}) : defaults.{fallback}, 1),\n")
print("Applied exact-preimage fixes to five production modules; no threshold/default changes.")
