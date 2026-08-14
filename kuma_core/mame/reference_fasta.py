"""One rule about how many records a reference FASTA may hold.

A reference is ONE molecule. Every reader in this repo used to drop ``>`` lines
and join what was left, so a file carrying a plasmid backbone and a target gene
came back as one sequence with a junction that exists in no molecule, and every
span, coordinate and verdict downstream was computed against that chimera with
no warning anywhere.

The judgement lives here rather than in each reader because there are three of
them across two layers (``kuma_core.mame.ingest.amplicon_reference``,
``kuma_core.mame.pipeline`` and the sidecar ``analyze`` handler) and the
operator must not see a different sentence depending on which path read the
file. Only the judgement is shared: each reader keeps its own I/O, since they
differ deliberately in encoding strictness.

This module imports nothing beyond the standard library and lives directly
under ``kuma_core.mame`` (whose ``__init__`` is a docstring) so the sidecar can
import it without pulling in the whole ``ingest`` package.
"""

from __future__ import annotations

from collections.abc import Iterable

#: How many record names to quote before the message is cut short. A file with
#: dozens of records is a database rather than a reference, and listing all of
#: them buries the sentence that says what to do about it.
_MAX_NAMED_RECORDS = 8


def multi_record_reason(lines: Iterable[str]) -> str | None:
    """Return the refusal reason when *lines* hold several FASTA records.

    ``None`` means the content is acceptable as a reference: exactly one record,
    or none at all. A file with no header is still accepted because a bare
    sequence file is a supported input and always was, and counting its records
    as zero says nothing about how many molecules it holds.

    The caller raises: the reason is a bare sentence with no path in it, so each
    layer can wrap it in whichever error type it already uses while the operator
    reads the same words.
    """
    headers = [line.strip() for line in lines if line.startswith(">")]
    if len(headers) <= 1:
        return None
    # First whitespace-delimited token, the conventional record id. An empty
    # header keeps a placeholder rather than vanishing, so the names listed
    # always number the same as the count stated beside them.
    names = [(header[1:].strip().split() or ["(unnamed)"])[0] for header in headers]
    shown = names[:_MAX_NAMED_RECORDS]
    listed = ", ".join(shown)
    if len(names) > len(shown):
        listed += f", ... (+{len(names) - len(shown)} more)"
    return (
        f"Reference FASTA holds {len(headers)} sequence records ({listed}); "
        "a reference must be a single molecule. Supply a file containing "
        "only the record reads are aligned against"
    )


__all__ = ["multi_record_reason"]
