#!/usr/bin/env python3
"""Produce real KURO capture data by driving the built sidecar over JSON-RPC.

Everything written to scripts/real-data.json comes back from the sidecar
binary in src-tauri/binaries. No value is hand-written here, so the capture
screens that consume this file show sidecar output rather than fixtures.

Inputs are the real IspS records used in the lab:
  pTSN-PtIspS-idi(KanR)_corrected.gb   plasmid carrying PtIspS
  df_test.csv                          EVOLVEpro predictions over that CDS

Usage:
    .venv/bin/python scripts/gen_real_capture_data.py [--out scripts/real-data.json]
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_INPUT_DIR = Path.home() / "_workspace" / "999.kuma_record_input"
DEFAULT_GENBANK = DEFAULT_INPUT_DIR / "pTSN-PtIspS-idi(KanR)_corrected.gb"
DEFAULT_EVOLVEPRO = DEFAULT_INPUT_DIR / "df_test.csv"

# Design parameters mirror the KURO defaults carried in the autosaved
# workspace at ~/Documents/kuma/260731_hmk_test/.autosave/kuro.json.
POLYMERASE = "KOD"
CODON_STRATEGY = "closest"
ORGANISM = "ecoli"
TM_FWD = 62.0
TM_REV = 58.0
TM_OVERLAP = 42.0
ROUND_SIZE = 96
TOP_N = 95


def sidecar_path() -> Path:
    machine = platform.machine()
    arch = "aarch64" if machine in {"arm64", "aarch64"} else "x86_64"
    system = platform.system()
    if system == "Darwin":
        triple = f"{arch}-apple-darwin"
    elif system == "Linux":
        triple = f"{arch}-unknown-linux-gnu"
    else:
        triple = f"{arch}-pc-windows-msvc.exe"
    return ROOT / "src-tauri" / "binaries" / f"kuro-sidecar-{triple}"


class Sidecar:
    """Line-delimited JSON-RPC client over the sidecar stdio pipe."""

    def __init__(self, binary: Path) -> None:
        self._proc = subprocess.Popen(  # noqa: S603
            [str(binary)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        self._next_id = 0

    def call(self, method: str, params: dict, timeout_s: float = 900.0) -> dict:
        self._next_id += 1
        request_id = self._next_id
        payload = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        assert self._proc.stdin is not None
        assert self._proc.stdout is not None
        self._proc.stdin.write(json.dumps(payload) + "\n")
        self._proc.stdin.flush()

        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            line = self._proc.stdout.readline()
            if not line:
                raise RuntimeError(f"{method}: sidecar closed the pipe")
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise RuntimeError(f"{method}: {json.dumps(message['error'], ensure_ascii=False)}")
            return message["result"]
        raise TimeoutError(f"{method}: no response within {timeout_s}s")

    def close(self) -> None:
        try:
            self.call("shutdown", {}, timeout_s=10.0)
        except Exception:  # noqa: BLE001 - shutdown is best effort
            pass
        assert self._proc.stdin is not None
        self._proc.stdin.close()
        try:
            self._proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self._proc.kill()


def pick_target_cds(genes: list[dict]) -> dict:
    """The IspS CDS is the longest coding region on this plasmid."""
    coding = [g for g in genes if g.get("aa_length")]
    if not coding:
        raise RuntimeError("no CDS with a translation found in the GenBank record")
    return max(coding, key=lambda g: g["aa_length"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--genbank", type=Path, default=DEFAULT_GENBANK)
    parser.add_argument("--evolvepro", type=Path, default=DEFAULT_EVOLVEPRO)
    parser.add_argument("--out", type=Path, default=ROOT / "scripts" / "real-data.json")
    args = parser.parse_args()

    for label, path in (("genbank", args.genbank), ("evolvepro", args.evolvepro)):
        if not path.is_file():
            sys.stderr.write(f"missing {label} input: {path}\n")
            return 2

    binary = sidecar_path()
    if not binary.is_file():
        sys.stderr.write(f"sidecar not built: {binary}\nRun: pnpm run sidecar:build\n")
        return 2

    sidecar = Sidecar(binary)
    try:
        seq_info = sidecar.call("load_fasta", {"filepath": str(args.genbank)})
        target = pick_target_cds(seq_info["genes"])
        ref_seq = target.get("translation", "")
        sys.stdout.write(
            f"[real-data] target CDS {target['cds_start']}..{target['cds_end']} "
            f"({target['aa_length']} aa)\n"
        )

        evolvepro = sidecar.call(
            "load_evolvepro_csv",
            {
                "filepath": str(args.evolvepro),
                "top_n": TOP_N,
                "round_size": ROUND_SIZE,
                "ref_seq": ref_seq,
            },
        )
        variants = evolvepro.get("selected_variants") or evolvepro.get("variants") or []
        sys.stdout.write(f"[real-data] EVOLVEpro selected {len(variants)} variants\n")
        if not variants:
            raise RuntimeError("load_evolvepro_csv returned no variants")

        mutation_text = "\n".join(
            v if isinstance(v, str) else v.get("variant", "") for v in variants
        )
        design = sidecar.call(
            "design_sdm_primers",
            {
                "fasta_path": str(args.genbank),
                "target_start": target["cds_start"],
                "mutations_csv_or_text": mutation_text,
                "polymerase": POLYMERASE,
                "codon_strategy": CODON_STRATEGY,
                "organism": ORGANISM,
                "tm_fwd_target": TM_FWD,
                "tm_rev_target": TM_REV,
                "tm_overlap_target": TM_OVERLAP,
            },
        )
        sys.stdout.write(
            f"[real-data] design {design['success_count']}/{design['total_count']} succeeded, "
            f"{len(design.get('failed_mutations') or [])} failed\n"
        )

        plate = sidecar.call("get_plate_map", {})
        sys.stdout.write(f"[real-data] plate mappings {len(plate.get('mappings') or [])}\n")

        # The export step previews both liquid-handler layouts, and the status
        # bar asks the sidecar for its health. Recording them keeps MOCK_MODE
        # text out of the captured frames.
        echo_dry_run = sidecar.call("export_echo_mapping_dry_run", {})
        janus_dry_run = sidecar.call("export_janus_mapping_dry_run", {})
        health = sidecar.call("health_info", {})
        settings = sidecar.call("settings_load", {})

        polymerases = sidecar.call("list_polymerases", {})
        # The parameter panel asks for the full profile of each listed enzyme,
        # so the capture stub needs one recorded reply per name.
        polymerase_details = {
            entry["name"]: sidecar.call("get_polymerase_details", {"name": entry["name"]})
            for entry in polymerases
            if isinstance(entry, dict) and entry.get("name")
        }
        organisms = sidecar.call("list_organisms", {})
        # The mutation step previews the source table before column mapping.
        evolvepro_preview = sidecar.call(
            "preview_evolvepro_source", {"filepath": str(args.evolvepro)}
        )

        # UniProt and InterPro are network lookups. They are optional for the
        # capture run, so a failure downgrades to an empty section rather than
        # aborting the whole bundle.
        uniprot: dict = {"candidates": []}
        domains: dict = {"domains": []}
        active_site: dict = {"accession": "", "active_site_positions": [], "binding_positions": []}
        structures: dict = {}
        pdb_text: dict = {}
        try:
            uniprot = sidecar.call(
                "search_uniprot",
                {"translation": ref_seq, "gene_name": "ispS", "organism": ""},
                timeout_s=180.0,
            )
            candidates = uniprot.get("candidates") or []
            sys.stdout.write(f"[real-data] UniProt candidates {len(candidates)}\n")
            if candidates:
                accession = candidates[0]["accession"]
                domains = sidecar.call("fetch_domains", {"accession": accession}, timeout_s=180.0)
                sys.stdout.write(
                    f"[real-data] InterPro domains for {accession}: "
                    f"{len(domains.get('domains') or [])}\n"
                )
                structures = sidecar.call(
                    "check_structures_available", {"accessions": [accession]}, timeout_s=180.0
                )
                pdb_text = sidecar.call(
                    "fetch_pdb_text", {"accession": accession}, timeout_s=300.0
                )
                sys.stdout.write(
                    f"[real-data] structure text for {accession}: "
                    f"{len(json.dumps(pdb_text))} bytes\n"
                )
                active_site = sidecar.call(
                    "fetch_active_site_residues", {"accession": accession}, timeout_s=180.0
                )
                sys.stdout.write(
                    f"[real-data] active site positions: "
                    f"{len(active_site.get('active_site_positions') or [])}, "
                    f"binding: {len(active_site.get('binding_positions') or [])}\n"
                )
        except (RuntimeError, TimeoutError) as exc:
            sys.stdout.write(f"[real-data] network lookup skipped: {exc}\n")

        bundle = {
            "generated_by": "scripts/gen_real_capture_data.py",
            "sidecar": binary.name,
            "inputs": {
                "genbank": str(args.genbank),
                "evolvepro": str(args.evolvepro),
            },
            "design_params": {
                "polymerase": POLYMERASE,
                "codon_strategy": CODON_STRATEGY,
                "organism": ORGANISM,
                "tm_fwd_target": TM_FWD,
                "tm_rev_target": TM_REV,
                "tm_overlap_target": TM_OVERLAP,
                "target_start": target["cds_start"],
                "top_n": TOP_N,
                "round_size": ROUND_SIZE,
            },
            "target_cds": target,
            "seq_info": seq_info,
            "evolvepro": evolvepro,
            "design": design,
            "plate": plate,
            "polymerases": polymerases,
            "polymerase_details": polymerase_details,
            "organisms": organisms,
            "evolvepro_preview": evolvepro_preview,
            "echo_dry_run": echo_dry_run,
            "janus_dry_run": janus_dry_run,
            "health": health,
            "settings": settings,
            "uniprot": uniprot,
            "domains": domains,
            "active_site": active_site,
            "structures": structures,
            "pdb_text": pdb_text,
        }
    finally:
        sidecar.close()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    sys.stdout.write(f"[real-data] wrote {args.out.relative_to(ROOT)}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
