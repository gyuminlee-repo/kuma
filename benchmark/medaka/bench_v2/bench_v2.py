"""
kuma-mame consensus accuracy benchmark v2
- WT reference: 현실 비반복 backbone (177bp) + 2 homopolymer runs
- WT sanity gate: G1 well ed <= 2 (N 제외) at depth >= 30x
- output: bench_v2/ 전용
"""

import datetime
import gzip
import logging
import os
import re
import shutil
import subprocess
import sys
import traceback
from pathlib import Path

# paths
REPO = Path(__file__).resolve().parents[3]
BADREAD = Path(os.environ.get("BADREAD", shutil.which("badread") or "badread"))
# Written outside the committed tree so a rerun does not overwrite report.md here.
OUT = Path(os.environ.get("BENCH_V2_OUT", "bench_v2_out"))
OUT.mkdir(parents=True, exist_ok=True)
REPORT = OUT / "report.md"

# setup python path and minimap2 visibility before importing kuma_core
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "python-core"))
# minimap2 must be on PATH (the original run prepended /opt/homebrew/bin).

import edlib  # noqa: E402
from openpyxl import Workbook  # noqa: E402

from kuma_core.mame.ingest.run_pipeline import ingest_run_folder  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
log = logging.getLogger(__name__)

# barcode sequences
_F = [
    "AATCCCACTAC", "TGAACTGAGCG", "TATCTGACCTT", "ATATGAGACG",
    "CGCTCATTAG",  "TAATCTCGTC",  "GCGCGATTTT",  "AGAGCACTAG",
    "TGCCTTGATC",  "CTACTCAGTC",  "TCGTCTGACT",  "GAACATACGG",
]
_R = [
    "CCCTATGACA", "TAATGGCAAG", "AACAAGGCGT", "GTATGTAGAA",
    "TTCTATGGGG", "CCTCGCAACC", "TGGATGCTTA", "AGAGTGCGGC",
]
_FT = "CACAGGAGGTTAAACC"
_RT = "TGCGTTGCGCTCTAG"


def rc(s):
    return s.translate(str.maketrans("ACGTacgt", "TGCAtgca"))[::-1]


def construct(f_idx, r_idx, amp):
    """f_idx/r_idx: 0-based"""
    return _F[f_idx] + _FT + amp + rc(_RT) + rc(_R[r_idx])


# ---------------------------------------------------------------------------
# WT amplicon: 현실 비반복 backbone (177bp)
# 지시: backbone에서 pos 60에 AAAAAA 치환 -> A-run 7bp (index 60-66)
#       pos 120에 TTTTTT 치환 -> T-run 7bp (index 120-126)
# trim_flank_bp=30 기준 trim-safe zone [30,147) 내 모든 run 포함
# ---------------------------------------------------------------------------
WT_AMP = (
    "ATGGTGTTCAAGAACTTCGATGCGCTGACC"   # 0-29  (비반복)
    "GGCAAAGACCTGAAAGAGTTCGCGAAATCG"   # 30-59 (비반복)
    "AAAAAAATGAACCTGAACAAGCTGAAAGCG"   # 60-89 (A-run at 60-66, 7bp)
    "TTCAACCAGTTCGCGAACATGAAAGCGTTC"   # 90-119 (비반복)
    "TTTTTTTACTTCAACAAGATCTTCAACAAG"   # 120-149 (T-run at 120-126, 7bp)
    "TTCGCGAACATGAACAAGTTCAAC"         # 150-173 (비반복)
    "TGA"                               # 174-176 (stop codon)
)
assert len(WT_AMP) == 177, f"WT_AMP length={len(WT_AMP)}, expected 177"

# detect actual homopolymer runs (assert)
_a_runs = [(m.start(), m.end()) for m in re.finditer(r"A{4,}", WT_AMP)]
_t_runs = [(m.start(), m.end()) for m in re.finditer(r"T{4,}", WT_AMP)]
assert len(_a_runs) == 1, f"Expected 1 A-run, found {_a_runs}"
assert len(_t_runs) == 1, f"Expected 1 T-run, found {_t_runs}"
_A_RUN_START, _A_RUN_END = _a_runs[0]   # (60, 67)
_T_RUN_START, _T_RUN_END = _t_runs[0]   # (120, 127)
_TRIM_SAFE_START = 30
_TRIM_SAFE_END   = len(WT_AMP) - 30     # 147

# G3: T-run 직전 위치 (adjacent SNV)
_G3_SNV_POS = _T_RUN_START - 1          # 119
assert _TRIM_SAFE_START <= _G3_SNV_POS < _TRIM_SAFE_END, f"G3 SNV pos {_G3_SNV_POS} not trim-safe"

# G5: A-run 내부 결실 위치
_G5_DEL_POS = _A_RUN_START + 2          # 62
assert _TRIM_SAFE_START <= _G5_DEL_POS < _TRIM_SAFE_END, f"G5 del pos {_G5_DEL_POS} not trim-safe"

# G2: 비-homopolymer SNV 3개 위치 (95, 105, 135)
_G2_SNVS = [95, 105, 135]
for _p in _G2_SNVS:
    in_a = any(s <= _p < e for s, e in _a_runs)
    in_t = any(s <= _p < e for s, e in _t_runs)
    assert not in_a and not in_t, f"G2 pos {_p} inside homopolymer run"
    assert _TRIM_SAFE_START <= _p < _TRIM_SAFE_END, f"G2 pos {_p} not trim-safe"

# G4: 비-homopolymer 2bp 결실 [80, 82)
_G4_DEL_START = 80
for _p in [_G4_DEL_START, _G4_DEL_START + 1]:
    in_a = any(s <= _p < e for s, e in _a_runs)
    in_t = any(s <= _p < e for s, e in _t_runs)
    assert not in_a and not in_t, f"G4 del pos {_p} inside homopolymer run"
assert _TRIM_SAFE_START <= _G4_DEL_START and _G4_DEL_START + 2 <= _TRIM_SAFE_END


def apply_g2(amp):
    """3 SNVs at pos 95, 105, 135 (non-homopolymer)"""
    a = list(amp)
    a[95]  = "T" if amp[95]  != "T" else "A"
    a[105] = "T" if amp[105] != "T" else "A"
    a[135] = "T" if amp[135] != "T" else "A"
    return "".join(a)


def apply_g3(amp):
    """1 SNV adjacent to T-run at pos _G3_SNV_POS (119)"""
    a = list(amp)
    a[_G3_SNV_POS] = "G" if amp[_G3_SNV_POS] != "G" else "A"
    return "".join(a)


def apply_g4(amp):
    """2bp deletion at pos _G4_DEL_START (80-81), non-homopolymer"""
    return amp[:_G4_DEL_START] + amp[_G4_DEL_START + 2:]


def apply_g5(amp):
    """1bp deletion inside A-run at pos _G5_DEL_POS (62)"""
    return amp[:_G5_DEL_POS] + amp[_G5_DEL_POS + 1:]


WELL_DESIGNS = {
    "G1": {"f": 0,  "r": 0, "amp": WT_AMP,           "type": "WT"},
    "G2": {"f": 2,  "r": 1, "amp": apply_g2(WT_AMP), "type": "SNV3"},
    "G3": {"f": 6,  "r": 3, "amp": apply_g3(WT_AMP), "type": "HomoAdjacentSNV"},
    "G4": {"f": 11, "r": 7, "amp": apply_g4(WT_AMP), "type": "Del2bp"},
    "G5": {"f": 4,  "r": 5, "amp": apply_g5(WT_AMP), "type": "HomoDel1bp"},
}

DEPTHS = [10, 20, 30, 50, 100]


def build_constructs():
    log.info("[bench] Building constructs...")
    c_map = {}
    for gid, d in WELL_DESIGNS.items():
        c = construct(d["f"], d["r"], d["amp"])
        c_map[gid] = c
        log.info("  %s (%s): construct_len=%d, amp_len=%d", gid, d["type"], len(c), len(d["amp"]))
    return c_map


def make_barcodes_xlsx(path: Path):
    wb = Workbook()
    ws = wb.active
    ws.title = "barcodes"
    for i in range(1, 13):
        ws.append([f"isps_f_{i}", (_F[i-1] + _FT).lower()])
    for i in range(1, 9):
        ws.append([f"isps_r_{i}", (_R[i-1] + _RT).lower()])
    wb.save(path)


def best_frame(query, candidates):
    """Return (min_dist, frame_name) from candidate dict."""
    best = (len(query) + 1, "none")
    for name, ref in candidates.items():
        r = edlib.align(query, ref, task="distance", mode="NW")
        d = r["editDistance"]
        if d < best[0]:
            best = (d, name)
    return best


def call_variants_from_cigar(consensus, reference, result_with_path):
    """Parse edlib CIGAR, return (snvs, insertions, deletions)."""
    if result_with_path["editDistance"] < 0:
        return [], [], []
    cigar = result_with_path.get("cigar", "")
    if not cigar:
        return [], [], []
    snvs, insertions, deletions = [], [], []
    r_pos, c_pos = 0, 0
    i = 0
    while i < len(cigar):
        j = i
        while j < len(cigar) and cigar[j].isdigit():
            j += 1
        count = int(cigar[i:j]) if j > i else 1
        op = cigar[j]
        i = j + 1
        if op == "=":
            r_pos += count
            c_pos += count
        elif op == "X":
            for k in range(count):
                snvs.append((r_pos + k, reference[r_pos + k], consensus[c_pos + k]))
            r_pos += count
            c_pos += count
        elif op == "I":
            insertions.append((r_pos, "-", consensus[c_pos:c_pos+count]))
            c_pos += count
        elif op == "D":
            for k in range(count):
                deletions.append((r_pos + k, reference[r_pos + k], "-"))
            r_pos += count
    return snvs, insertions, deletions


def truth_for_well(gid, frame_name):
    amp = WELL_DESIGNS[gid]["amp"]
    if frame_name == "amp":
        return amp
    if frame_name == "amp_trim30":
        return amp[30:-30]
    if frame_name == "rc_amp":
        return rc(amp)
    if frame_name == "rc_amp_trim30":
        return rc(amp)[30:-30]
    return amp


def score_depth(depth, read_len_mean, templates_fa, barcodes_xlsx, ref_fa):
    log.info("\n[bench] === depth %dx ===", depth)
    depth_dir = OUT / f"depth_{depth}"
    depth_dir.mkdir(exist_ok=True)
    log_badread = depth_dir / "badread.log"
    reads_raw = depth_dir / "reads.fastq"
    run_dir = depth_dir / "run_dir"
    fastq_pass = run_dir / "fastq_pass"
    fastq_pass.mkdir(parents=True, exist_ok=True)
    out_dir = depth_dir / "mame_out"
    out_dir.mkdir(exist_ok=True)

    # simulate reads
    cmd_badread = [
        str(BADREAD), "simulate",
        "--reference", str(templates_fa),
        "--quantity", f"{depth * len(WELL_DESIGNS)}x",
        "--length", f"{read_len_mean},50",
        "--junk_reads", "0",
        "--random_reads", "0",
        "--chimeras", "0",
        "--seed", "1",
    ]
    log.info("  [badread] running %dx ...", depth)
    with open(reads_raw, "w") as reads_fh, open(log_badread, "w") as logf:
        ret = subprocess.run(cmd_badread, stdout=reads_fh, stderr=logf)  # noqa: S603
    if ret.returncode != 0:
        log.error("  [ERROR] badread failed at %dx -- see %s", depth, log_badread)
        return {"error": "badread failed"}

    # gzip reads
    with open(reads_raw, "rb") as f_in, gzip.open(fastq_pass / "reads.fastq.gz", "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)
    log.info("  [badread] reads gzipped")

    # run ingest_run_folder
    log.info("  [mame] ingest_run_folder ...")
    try:
        records = ingest_run_folder(
            run_dir=run_dir,
            custom_barcodes_xlsx=barcodes_xlsx,
            reference_fasta=ref_fa,
            demux_output_dir=out_dir,
            native_barcodes=None,
            mapq_threshold=0,
            coverage_fraction=0.5,
            trim_flank_bp=30,
            min_depth=1,
        )
        log.info("  [mame] got %d records", len(records))
    except Exception as e:
        log.error("  [ERROR] ingest_run_folder exception: %s", e)
        traceback.print_exc()
        return {"error": str(e)}

    # map custom_barcode to gid (format: "{R}_{F}" 1-indexed)
    cb_to_gid = {}
    for gid, d in WELL_DESIGNS.items():
        r1 = d["r"] + 1
        f1 = d["f"] + 1
        cb_to_gid[f"{r1}_{f1}"] = gid

    depth_res = {}
    for rec in records:
        cb = rec.custom_barcode
        gid = cb_to_gid.get(cb)
        if gid is None:
            continue
        depth_res[gid] = {
            "consensus_seq": rec.consensus_seq,
            "read_count": rec.read_count,
            "n_frac": rec.consensus_n_fraction,
        }
        log.info(
            "    %s (%s): reads=%s, n_frac=%.3f, cons_len=%d",
            gid, cb, rec.read_count, rec.consensus_n_fraction, len(rec.consensus_seq),
        )

    log.info("  [mame] matched %d/%d wells", len(depth_res), len(WELL_DESIGNS))

    if "G1" not in depth_res:
        log.warning("  [WARN] G1 (WT) not recovered")
        return {"error": "G1 missing", "depth_res": depth_res}

    # WT sanity gate: N wildcard edlib, 4-frame 최소
    g1_cons_seq = depth_res["G1"]["consensus_seq"]
    wt_truth_frames = {
        "amp":           WT_AMP,
        "amp_trim30":    WT_AMP[30:-30],
        "rc_amp":        rc(WT_AMP),
        "rc_amp_trim30": rc(WT_AMP)[30:-30],
    }
    equalities = [("N","A"),("N","C"),("N","G"),("N","T")]
    best_gate_dist = len(g1_cons_seq) + 1
    best_gate_frame = "none"
    for fname, fseq in wt_truth_frames.items():
        r_gate = edlib.align(g1_cons_seq, fseq, task="distance", mode="NW",
                             additionalEqualities=equalities)
        d_gate = r_gate["editDistance"]
        if d_gate < best_gate_dist:
            best_gate_dist = d_gate
            best_gate_frame = fname
    gate_passed = (best_gate_dist <= 2)
    n_count_g1 = g1_cons_seq.count("N")
    log.info("  [gate] G1 WT sanity: frame=%s ed=%d (N=%d) passed=%s",
             best_gate_frame, best_gate_dist, n_count_g1, gate_passed)

    if depth >= 30 and not gate_passed:
        log.error("  [GATE FAIL] depth=%dx WT ed=%d > 2 -- halting", depth, best_gate_dist)
        return {
            "gate_fail": True,
            "gate_ed": best_gate_dist,
            "gate_frame": best_gate_frame,
            "gate_n_count": n_count_g1,
            "depth": depth,
        }

    # scoring frame: N->A 치환 후 4-frame 최단
    g1_cons_no_n = g1_cons_seq.replace("N", "A")
    best_dist, best_frame_name = best_frame(g1_cons_no_n, wt_truth_frames)
    log.info("  [frame] G1 best_frame=%s (edit_dist=%d)", best_frame_name, best_dist)

    # score each well
    gid_scores = {}
    for gid in WELL_DESIGNS:
        if gid not in depth_res:
            gid_scores[gid] = {"status": "not_recovered"}
            continue
        cons = depth_res[gid]["consensus_seq"]
        truth = truth_for_well(gid, best_frame_name)
        cons_no_n = cons.replace("N", "A")
        r = edlib.align(cons_no_n, truth, task="path", mode="NW")
        edit_dist = r["editDistance"]
        snvs, insertions, deletions = call_variants_from_cigar(cons_no_n, truth, r)
        n_count = cons.count("N")

        gid_scores[gid] = {
            "status": "perfect" if edit_dist == 0 else "imperfect",
            "edit_dist_to_truth": edit_dist,
            "n_count": n_count,
            "n_frac": depth_res[gid]["n_frac"],
            "read_count": depth_res[gid]["read_count"],
            "false_snvs_vs_truth": len(snvs),
            "false_ins_vs_truth": len(insertions),
            "false_del_vs_truth": len(deletions),
            "consensus_len": len(cons),
            "truth_len": len(truth),
            "len_match": (len(cons) == len(truth)),
            "frame": best_frame_name,
        }

    return {
        "frame": best_frame_name,
        "gate_ed": best_gate_dist,
        "gate_n_count": n_count_g1,
        "gate_passed": gate_passed,
        "wells": gid_scores,
    }


def first_perfect_depth(gid_key, all_results):
    for d in DEPTHS:
        r = all_results.get(d, {})
        if "wells" in r:
            w = r["wells"].get(gid_key, {})
            if w.get("edit_dist_to_truth", 999) == 0:
                return d
    return None


def write_report(all_results, gate_halted_at=None):
    lines = []
    lines.append("# kuma-mame Consensus Accuracy Benchmark v2 Report")
    lines.append("")
    lines.append("## 가정 및 설계")
    lines.append("- 합성 데이터 (badread nanopore2023 모델, seed=1)")
    lines.append(f"- WT amplicon: {len(WT_AMP)}bp (현실 비반복 backbone + 2 homopolymer runs)")
    lines.append(f"  - A-run: [{_A_RUN_START},{_A_RUN_END}) {_A_RUN_END - _A_RUN_START}bp")
    lines.append(f"  - T-run: [{_T_RUN_START},{_T_RUN_END}) {_T_RUN_END - _T_RUN_START}bp")
    lines.append(f"  - 서열: {WT_AMP}")
    lines.append("- ingest_run_folder 파라미터: mapq_threshold=0, coverage_fraction=0.5, trim_flank_bp=30, min_depth=1")
    lines.append("- Consensus frame: G1(WT) well에 대해 4-frame edlib 최소 거리 자동 결정")
    lines.append("- WT sanity gate: G1 well N wildcard edlib ed <= 2 (depth>=30x 실패시 결과표 생성 중단)")
    lines.append("")
    lines.append("## Well 설계")
    lines.append("| Well | Barcode (F,R) | custom_barcode | 유형 | amp_len | 변이 위치 |")
    lines.append("|------|--------------|----------------|------|---------|----------|")
    variant_info = {
        "G1": "없음",
        "G2": f"SNV pos {_G2_SNVS[0]},{_G2_SNVS[1]},{_G2_SNVS[2]} (비-homopolymer)",
        "G3": f"SNV pos {_G3_SNV_POS} (T-run 직전)",
        "G4": f"2bp del [{_G4_DEL_START},{_G4_DEL_START+2}) (비-homopolymer)",
        "G5": f"1bp del pos {_G5_DEL_POS} (A-run 내부)",
    }
    for gid, d in WELL_DESIGNS.items():
        r1 = d["r"] + 1
        f1 = d["f"] + 1
        lines.append(f"| {gid} | F{f1},R{r1} | {r1}_{f1} | {d['type']} | {len(d['amp'])} | {variant_info[gid]} |")
    lines.append("")

    # WT sanity gate 결과표
    lines.append("## WT Sanity Gate 결과")
    lines.append("| Depth | G1 WT ed (N wildcard) | G1 N수 | Gate 판정 |")
    lines.append("|-------|----------------------|--------|----------|")
    for depth in DEPTHS:
        r = all_results.get(depth, {})
        if not r:
            lines.append(f"| {depth}x | - | - | 미실행 |")
            continue
        if "gate_fail" in r:
            ed = r.get("gate_ed", "?")
            nc = r.get("gate_n_count", "?")
            lines.append(f"| {depth}x | {ed} | {nc} | **FAIL** |")
        elif "error" in r:
            lines.append(f"| {depth}x | - | - | ERR: {r['error']} |")
        else:
            ed = r.get("gate_ed", "?")
            nc = r.get("gate_n_count", "?")
            gp = r.get("gate_passed", False)
            label = "PASS" if gp else "WARN(depth<30)"
            lines.append(f"| {depth}x | {ed} | {nc} | {label} |")
    lines.append("")

    if gate_halted_at is not None:
        r_fail = all_results.get(gate_halted_at, {})
        ed = r_fail.get("gate_ed", "?")
        nc = r_fail.get("gate_n_count", "?")
        lines.append(f"**WT sanity gate 실패: ed={ed} at depth {gate_halted_at}x, G1 N수={nc}**")
        lines.append("")
        lines.append("gate 실패로 이 depth 이후 결과표를 생성하지 않음.")
        lines.append("")
        lines.append("## 한계")
        lines.append("- 합성 데이터(badread nanopore2023): 실 MinKNOW 런 아님.")
        lines.append("- WT sanity gate 실패 -- reference 또는 harness 문제로 추정.")
        lines.append(f"*생성 시각: {datetime.datetime.now().isoformat()}*")
        with open(REPORT, "w") as f:
            f.write("\n".join(lines))
        return

    # 결과표
    lines.append("## 회수율 요약표")
    lines.append("")
    lines.append("| Depth | G1(WT) | G2(SNV3) | G3(HomoAdj) | G4(Del2bp) | G5(HomoDel) |")
    lines.append("|-------|--------|----------|-------------|------------|-------------|")
    for depth in DEPTHS:
        r = all_results.get(depth, {})
        if not r or ("error" in r and "wells" not in r) or "gate_fail" in r:
            lines.append(f"| {depth}x | ERR/GATE | | | | |")
            continue
        wells = r.get("wells", {})
        row = []
        for gid in ["G1", "G2", "G3", "G4", "G5"]:
            if gid not in wells:
                row.append("missing")
            elif wells[gid]["status"] == "not_recovered":
                row.append("not_recovered")
            else:
                ed = wells[gid]["edit_dist_to_truth"]
                row.append("OK" if ed == 0 else f"ed={ed}")
        lines.append("| " + str(depth) + "x | " + " | ".join(row) + " |")
    lines.append("")
    lines.append("## 상세 결과 (depth별)")
    lines.append("")
    for depth in DEPTHS:
        lines.append(f"### {depth}x")
        r = all_results.get(depth, {})
        if not r or ("error" in r and "wells" not in r) or "gate_fail" in r:
            lines.append("- SKIP/ERROR/GATE FAIL")
            lines.append("")
            continue
        frame = r.get("frame", "unknown")
        lines.append(f"- Consensus frame: **{frame}**")
        lines.append(f"- WT gate: ed={r.get('gate_ed','?')} N={r.get('gate_n_count','?')} {'PASS' if r.get('gate_passed') else 'WARN'}")
        lines.append("")
        lines.append("| Well | 유형 | reads | edit_dist | false_SNV | false_Ins | false_Del | N수 | len_match |")
        lines.append("|------|------|-------|-----------|-----------|-----------|-----------|-----|-----------|")
        for gid in WELL_DESIGNS:
            dtype = WELL_DESIGNS[gid]["type"]
            if gid not in r.get("wells", {}):
                lines.append(f"| {gid} | {dtype} | - | - | - | - | - | - | - |")
                continue
            w = r["wells"][gid]
            if w["status"] == "not_recovered":
                lines.append(f"| {gid} | {dtype} | 0 | n/a | n/a | n/a | n/a | n/a | n/a |")
            else:
                lm = "yes" if w["len_match"] else f"no(c={w['consensus_len']},t={w['truth_len']})"
                lines.append(
                    f"| {gid} | {dtype} | {w['read_count']} | {w['edit_dist_to_truth']} "
                    f"| {w['false_snvs_vs_truth']} | {w['false_ins_vs_truth']} "
                    f"| {w['false_del_vs_truth']} | {w['n_count']} | {lm} |"
                )
        lines.append("")

    lines.append("## 결론")
    lines.append("")
    snv_d  = first_perfect_depth("G2", all_results)
    hadj_d = first_perfect_depth("G3", all_results)
    del2_d = first_perfect_depth("G4", all_results)
    hdel_d = first_perfect_depth("G5", all_results)
    lines.append(f"- 일반 SNV (G2, 3개 SNV): 최초 완벽 회수 depth = **{snv_d}x**")
    lines.append(f"- Homopolymer 인접 SNV (G3): 최초 완벽 회수 depth = **{hadj_d}x**")
    lines.append(f"- 비-homopolymer 결실 (G4, 2bp del): 최초 완벽 회수 depth = **{del2_d}x**")
    lines.append(f"- Homopolymer 내 결실 (G5, 1bp polyA del): 최초 완벽 회수 depth = **{hdel_d}x**")
    lines.append("")
    lines.append("### 판정")
    if snv_d and snv_d <= 30:
        lines.append(f"- 충분: 일반 SNV는 {snv_d}x부터 안정적 회수.")
    elif snv_d:
        lines.append(f"- 주의: 일반 SNV도 {snv_d}x 필요.")
    else:
        lines.append("- 실패: 일반 SNV 회수 불가 (테스트 범위 초과 또는 파이프라인 오류).")
    if hadj_d and snv_d and hadj_d > snv_d:
        lines.append(f"- Homopolymer 인접 SNV(G3): 일반 SNV 대비 더 높은 depth({hadj_d}x) 필요.")
    elif hadj_d:
        lines.append(f"- Homopolymer 인접 SNV(G3): {hadj_d}x에서 회수.")
    else:
        lines.append("- Homopolymer 인접 SNV(G3): 10-100x 범위에서 완벽 회수 실패.")
    if hdel_d is None:
        lines.append("- 깨짐: Homopolymer 내 결실(G5)은 10-100x 범위에서 완벽 회수 실패.")
    else:
        lines.append(f"- 주의: Homopolymer 내 결실(G5) 회수에 {hdel_d}x 필요.")
    lines.append("")
    lines.append("## 한계")
    lines.append("- 합성 데이터(badread nanopore2023): 실 MinKNOW 런 아님.")
    lines.append("- Medaka head-to-head 비교 미수행 (macOS arm64 네이티브 Medaka 미설치).")
    lines.append("- 각 well당 단일 barcode 조합만 테스트.")
    lines.append("- edit_dist 기반 채점: 동일 위치 치환+삭제 동시 발생시 attribution 불완전.")
    lines.append("")
    lines.append(f"*생성 시각: {datetime.datetime.now().isoformat()}*")
    with open(REPORT, "w") as f:
        f.write("\n".join(lines))
    print("[bench] Report written.")


def main():
    log.info("[bench v2] WT_AMP: len=%d, A-run=[%d,%d), T-run=[%d,%d)",
             len(WT_AMP), _A_RUN_START, _A_RUN_END, _T_RUN_START, _T_RUN_END)

    constructs = build_constructs()
    mean_len = int(sum(len(v) for v in constructs.values()) / len(constructs))
    read_len_mean = mean_len + 70
    log.info("[bench] read_len_mean=%d (mean_construct=%d)", read_len_mean, mean_len)

    templates_fa = OUT / "templates.fasta"
    with open(templates_fa, "w") as fh:
        for gid, seq in constructs.items():
            fh.write(f">{gid}\n{seq}\n")
    log.info("[bench] templates.fasta written")

    barcodes_xlsx = OUT / "barcodes.xlsx"
    make_barcodes_xlsx(barcodes_xlsx)
    log.info("[bench] barcodes.xlsx written")

    ref_fa = OUT / "reference.fasta"
    with open(ref_fa, "w") as fh:
        fh.write(f">sispS_test\n{WT_AMP}\n")
    log.info("[bench] reference.fasta written (WT_AMP %dbp)", len(WT_AMP))

    all_results = {}
    gate_halted_at = None
    for depth in DEPTHS:
        result = score_depth(depth, read_len_mean, templates_fa, barcodes_xlsx, ref_fa)
        all_results[depth] = result
        if result.get("gate_fail"):
            gate_halted_at = depth
            log.error("[bench] WT sanity gate FAILED at depth=%dx -- stopping", depth)
            break

    write_report(all_results, gate_halted_at=gate_halted_at)
    log.info("[bench v2] DONE")


if __name__ == "__main__":
    main()
