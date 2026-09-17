"""Output checksum helper for kuma export handlers.

Computes SHA-256 of an exported file and writes a sibling ``.sha256`` file
in ``shasum -c`` / ``sha256sum --check`` compatible format:

    ``<hex>  <basename>\\n``  (two spaces: text-mode marker per GNU coreutils)

Usage::

    from kuma_core.shared.output_hash import write_output_checksum

    cpath = write_output_checksum(output_path)
    result["checksum_path"] = str(cpath)

The ``.sha256`` file is placed next to the output file:

    /out/primers.xlsx  →  /out/primers.xlsx.sha256
    /out/order.csv     →  /out/order.csv.sha256
"""

from __future__ import annotations

from pathlib import Path

from kuma_core.shared.atomic_write import atomic_write_text
from kuma_core.shared.run_manifest import compute_input_sha256


def write_output_checksum(output_path: Path, *, algorithm: str = "sha256") -> Path:
    """Compute SHA-256 of *output_path* and write a sibling checksum file.

    The checksum file is named ``<output_path.name>.sha256`` (extension
    appended, not replaced) so that ``shasum -c`` / ``sha256sum --check``
    can be invoked from the same directory.

    Format written::

        <hex>  <basename>\\n

    Two spaces separate the digest from the filename (text-mode marker
    required by GNU coreutils ``shasum -c``).

    Args:
        output_path: Path to the exported file. Must exist and be a file.
        algorithm: Reserved for future use; only ``"sha256"`` is supported.

    Returns:
        The resolved absolute path of the written ``.sha256`` file.

    Raises:
        FileNotFoundError: *output_path* does not exist.
        IsADirectoryError: *output_path* is a directory.
        ValueError: *algorithm* is not ``"sha256"``.
    """
    if algorithm != "sha256":
        raise ValueError(
            f"Unsupported algorithm {algorithm!r}. Only 'sha256' is supported."
        )

    output_path = Path(output_path).resolve()

    # compute_input_sha256 raises FileNotFoundError / IsADirectoryError if needed.
    hex_digest = compute_input_sha256(output_path)

    checksum_path = output_path.parent / (output_path.name + ".sha256")
    filename = output_path.name
    # Escape set is the intersection of what deployed checkers accept, not the
    # newest one's output format. GNU coreutils escapes "\\" and "\n" at least
    # since 8.32 (src/md5sum.c print_filename); src/digest.c added '\r' to that
    # set in 9.0, so a \r-escaped line is a format 8.32 has never heard of.
    # Measured on this branch: 8.32 --check answers "no properly formatted
    # SHA256 checksum lines found" (rc=1) for the \r-escaped line, while 9.4
    # --check accepts the literal CR (rc=0). ubuntu-22.04 ships 8.32 and this project builds on it,
    # so the literal CR is the only form both eras verify.
    # Known limit: a name whose final byte is CR has no form both accept, since
    # 9.0 strips a trailing CR from each line to support CRLF checksum files.
    escaped = any(character in filename for character in "\\\n")
    if escaped:
        filename = filename.replace("\\", "\\\\").replace("\n", "\\n")
    prefix = "\\" if escaped else ""
    # Two spaces: text-mode marker per GNU coreutils shasum convention.
    # newline="" suppresses translation: this file is consumed by external
    # checkers that treat everything after the two spaces as the filename, so a
    # CRLF here makes the name unresolvable on the platform that wrote it.
    # Published atomically for the reason atomic_write_text's own docstring
    # gives: an interrupted write leaves a truncated file that still exists,
    # and shasum -c answers on a partial digest line rather than declining, so
    # the failure appears as a mismatch on a file that is intact. The manifest
    # written beside this one already publishes that way.
    atomic_write_text(
        checksum_path,
        f"{prefix}{hex_digest}  {filename}\n",
        encoding="utf-8",
        newline="",
    )
    return checksum_path


__all__ = ["write_output_checksum"]
