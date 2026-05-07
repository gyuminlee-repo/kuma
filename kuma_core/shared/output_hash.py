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
    # Two spaces: text-mode marker per GNU coreutils shasum convention.
    checksum_path.write_text(
        f"{hex_digest}  {output_path.name}\n", encoding="utf-8"
    )
    return checksum_path


__all__ = ["write_output_checksum"]
