"""``mame.detect_native_barcodes`` JSON-RPC handler.

Scans the ``fastq_pass/`` directory of a MinKNOW run and reports which native
barcodes were actually used, purely from on-disk FASTQ volume (a fast,
decompression-free proxy for read count).

RPC method name: ``mame.detect_native_barcodes``
Registered in ``sidecar_mame.dispatcher._METHODS`` (synchronous: stat-only,
fast, so it is NOT registered as an async method).

Parameter schema
----------------
See :class:`sidecar_mame.models.DetectNativeBarcodesParams` for full field
documentation and validation rules.

Response schema
---------------
``fastq_pass``      (str)   Resolved path to the scanned ``fastq_pass/`` dir.
``min_share``       (float) Threshold used for the ``is_used`` flag.
``native_barcodes`` (list)  Per-barcode summaries (name, sort_barcode_name,
                            fastq_bytes, fastq_mb, share, is_used).
``used_count``      (int)   Number of barcodes flagged as used.
``total_count``     (int)   Total native barcode dirs found.
"""

from __future__ import annotations

from pathlib import Path


def handle_detect_native_barcodes(params: dict) -> dict:
    """Detect which native barcodes were used in a MinKNOW run, from FASTQ volume.

    Parameters
    ----------
    params:
        Raw JSON-RPC params dict validated via
        :class:`~sidecar_mame.models.DetectNativeBarcodesParams`.

    Returns
    -------
    dict
        Result dict matching the response schema documented in the module
        docstring.
    """
    from sidecar_mame.models import DetectNativeBarcodesParams

    p = DetectNativeBarcodesParams.model_validate(params)

    from kuma_core.mame.ingest.demux import detect_used_native_barcodes
    from kuma_core.mame.ingest.sort_barcode import _nb_to_sort_barcode_name

    fastq_pass = Path(p.minknow_run_dir) / "fastq_pass"
    if not fastq_pass.is_dir():
        raise FileNotFoundError(
            f"fastq_pass/ directory not found under {p.minknow_run_dir}"
        )

    usages = detect_used_native_barcodes(fastq_pass, min_share=p.min_share)
    barcodes = [
        {
            "name": u.name,
            "sort_barcode_name": _nb_to_sort_barcode_name(u.name),
            "fastq_bytes": u.fastq_bytes,
            "fastq_mb": round(u.fastq_bytes / 1048576, 1),
            "share": round(u.share, 4),
            "is_used": u.is_used,
        }
        for u in usages
    ]
    return {
        "fastq_pass": str(fastq_pass.resolve()),
        "min_share": p.min_share,
        "native_barcodes": barcodes,
        "used_count": sum(1 for u in usages if u.is_used),
        "total_count": len(usages),
    }


__all__ = ["handle_detect_native_barcodes"]
