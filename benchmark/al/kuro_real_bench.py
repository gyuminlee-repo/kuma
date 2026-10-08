"""Phase B-kuro REAL selector bench — evaluates kuma_core KURO production selectors
(domain_aware_select, pareto_diversity_select) on combinatorial multi-mut assays.

Extends al.real_epistatic_pilot by adding two REAL KURO acquisition arms:

  kuro_domain  – kuma_core.kuro.evolvepro.domain_aware_select
                 (domain-proportional quota + first-position binning)
  kuro_pareto  – kuma_core.kuro.evolvepro.pareto_diversity_select
                 (greedy maximin in 1-D position / 3-D Ca space)

Reference arms retained for comparison:
  embdiv       – greedy maximin in ESM-2 embedding space (Ca-free control)
  kuro_ca      – greedy maximin in Ca-centroid descriptor space (combo-aware)
  topn         – greedy top-N by predicted fitness (greedy baseline)

LIMITATION — first-position reduction
--------------------------------------
Both KURO functions extract a variant's residue position via

    re.compile(r"[A-Z](\\d+)[A-Z]").search(variant)

which returns the FIRST match only.  For a combo token like 'L59M:W60T:K64W'
the extracted position is 59 (the lowest, since combo IDs are sorted ascending
by position).  All KURO diversity / domain-binning logic therefore operates on
that single first-position proxy, ignoring the other substituted positions.
This is the REAL production behavior; we document it faithfully and do NOT
work around it.

Usage
-----
    python -m al.kuro_real_bench                    # all 3 assays (seeds=50)
    python -m al.kuro_real_bench --smoke            # synthetic quick-exit
    python -m al.kuro_real_bench --assay <csv> --accession <acc> [options]
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from al import metrics, stats
from al.domains import fetch_domains
from al.embed_cache import DEFAULT_MODEL, embed_variants
from al.proxy_rf import RF_KWARGS
from al.acquisition import select_indices
from al.real_epistatic import (
    CombinatorialOracle,
    canonical_combo_id,
    combo_al_step,
    combo_centroid_descriptor,
    combo_zero_shot_prior,
    parse_combo,
)

from kuma_core.kuro.alphafold import fetch_ca_coords
from kuma_core.kuro.evolvepro import (
    domain_aware_select,
    pareto_diversity_select,
    structural_diversity_select,
)

# ──────────────────────────────────────────────────────────────────────────────
# Documentation constant (referenced in output)
# ──────────────────────────────────────────────────────────────────────────────

FIRST_POSITION_REDUCTION_NOTE = (
    "domain_aware_select and pareto_diversity_select extract a variant's position via "
    "re.compile(r'[A-Z](\\d+)[A-Z]').search(variant), which returns the FIRST match only. "
    "For a combo token 'L59M:W60T:K64W' the extracted position is 59 (the lowest, since "
    "combo IDs are sorted ascending by position). All KURO diversity/domain logic operates "
    "on this single first-position proxy, ignoring all other substituted positions in the "
    "combo. This is the real production behavior, not a benchmark simplification."
)

# ──────────────────────────────────────────────────────────────────────────────
# Assay registry
# ──────────────────────────────────────────────────────────────────────────────

_HERE = Path(__file__).resolve().parent.parent  # benchmark/

DEFAULT_ASSAYS = [
    {
        "name": "F7YBW8_MESOW_Aakre_2015",
        "csv": str(_HERE / "data/DMS_substitutions/DMS_ProteinGym_substitutions/F7YBW8_MESOW_Aakre_2015.csv"),
        "accession": "F7YBW8",
    },
    {
        "name": "RASK_HUMAN_Weng_2022_abundance",
        "csv": str(_HERE / "data/DMS_substitutions/DMS_ProteinGym_substitutions/RASK_HUMAN_Weng_2022_abundance.csv"),
        "accession": "P01116",
    },
    {
        "name": "GRB2_HUMAN_Faure_2021",
        "csv": str(_HERE / "data/DMS_substitutions/DMS_ProteinGym_substitutions/GRB2_HUMAN_Faure_2021.csv"),
        "accession": "P62993",
    },
]

ARMS = (
    "topn", "ucb",
    "kuro_domain", "kuro_pareto", "embdiv", "kuro_ca",
    "kuro_domain_centroid", "kuro_pareto_centroid",
    "kuro_struct", "kuro_struct_blend",
)
COMPARISON_ARMS = (
    "kuro_domain", "kuro_pareto", "kuro_ca",
    "kuro_domain_centroid", "kuro_pareto_centroid",
    "kuro_struct", "kuro_struct_blend",
)  # each vs topn; kuro_struct-vs-ucb added separately


# ──────────────────────────────────────────────────────────────────────────────
# Data loader
# ──────────────────────────────────────────────────────────────────────────────

def _load_multimut(csv_path: str) -> tuple[dict[str, float], dict[str, str], str]:
    """Return (canonical_id->raw DMS_score, canonical_id->mutated_seq, wt_seq) for multi-mut rows."""
    df = pd.read_csv(csv_path, usecols=lambda c: c in {"mutant", "mutated_sequence", "DMS_score"})
    df = df.dropna(subset=["DMS_score"])
    df = df[df["mutant"].astype(str).str.contains(":")].copy()
    scores: dict[str, float] = {}
    seqs: dict[str, str] = {}
    for _m, _seq, _s in zip(df["mutant"], df["mutated_sequence"], df["DMS_score"], strict=True):
        cid = canonical_combo_id(parse_combo(str(_m)))
        scores[cid] = float(_s)
        seqs[cid] = str(_seq)
    # Reconstruct WT by reverting first variant's substitutions.
    any_m = next(iter(scores))
    seq = list(seqs[any_m])
    for mut in parse_combo(any_m):
        seq[mut[1] - 1] = mut[0]
    return scores, seqs, "".join(seq)


# ──────────────────────────────────────────────────────────────────────────────
# Core bench runner (one assay)
# ──────────────────────────────────────────────────────────────────────────────

def run_kuro_bench(
    assay_csv: str,
    uniprot_acc: str,
    *,
    pool: int = 400,
    n_seed: int = 10,
    batch: int = 10,
    rounds: int = 4,
    seeds: int = 50,
    cache_dir: str,
    domain_cache_dir: str,
    model: str = DEFAULT_MODEL,
) -> dict:
    """Run the combinatorial AL loop with all KURO arms on one assay.

    Parameters
    ----------
    assay_csv:
        Path to a ProteinGym multi-mut DMS CSV.
    uniprot_acc:
        Correct UniProt accession for the protein (NOT the assay-name token).
    pool:
        Maximum number of multi-mut variants to subsample (deterministic, seed=0).
    n_seed:
        Size of the R1 neutral seed batch (shared across all arms and seeds).
    batch:
        Variants selected per AL round.
    rounds:
        Number of AL rounds per seed.
    seeds:
        Number of independent seeds (random_state + surrogate variation).
    cache_dir:
        Directory for ESM-2 embedding cache files.
    domain_cache_dir:
        Directory for domain annotation JSON cache files.
    model:
        ESM-2 model name (default 35M; 650M is prohibited by policy).

    Returns
    -------
    dict
        Per-arm norm_best means, CVaR@20%, 9-cell decisions, metadata.
    """
    t0 = time.perf_counter()
    raw_all, seqs_all, wt = _load_multimut(assay_csv)

    # Deterministic pool subsample.
    rng0 = np.random.default_rng(0)
    all_ids = sorted(raw_all)
    sub_arr = rng0.choice(all_ids, size=min(pool, len(all_ids)), replace=False)
    sub: list[str] = sorted(sub_arr.tolist())
    raw = {i: raw_all[i] for i in sub}
    seqs = {i: seqs_all[i] for i in sub}

    # Embeddings — 35M ESM-2, cached per assay_id (no re-embed if cache hit).
    assay_id = Path(assay_csv).stem + f"_multimut{len(sub)}"
    emb = embed_variants(assay_id, seqs, cache_dir, model_name=model).loc[sub]

    # Ca coordinates (1-based).  None = structure unavailable for this accession.
    ca: list | None = None
    ca_resolved: int = 0
    ca_error: str | None = None
    try:
        ca = fetch_ca_coords(uniprot_acc)
        if ca is not None:
            ca_resolved = sum(1 for c in ca if c is not None)
    except Exception as exc:
        ca_error = f"{type(exc).__name__}: {exc}"

    # Domain annotations (for kuro_domain arm).
    domains: list[dict] | None = None
    domains_error: str | None = None
    domains_resolved: int = 0
    try:
        domains = fetch_domains(uniprot_acc, domain_cache_dir, allow_network=True)
        domains_resolved = len(domains)
    except Exception as exc:
        domains_error = f"{type(exc).__name__}: {exc}"

    domain_arm_skip = not domains  # skip kuro_domain when no domains available

    # Ca-centroid descriptors (permutation-invariant; positional fallback if no structure).
    desc = np.vstack([combo_centroid_descriptor(parse_combo(i), ca) for i in sub])
    desc_idx: dict[str, int] = {i: k for k, i in enumerate(sub)}

    # R1: fixed arm-neutral ESM-2 zero-shot Top-N batch.
    zs = combo_zero_shot_prior(wt, sub, model_name=model)
    r1 = [i for i, _ in sorted(zs.items(), key=lambda kv: (-kv[1], kv[0]))[:n_seed]]

    pool_ids = sub
    emb_np = {i: emb.loc[i].to_numpy(dtype=float) for i in pool_ids}
    budget = n_seed + batch * rounds

    finals: dict[str, list[float]] = {a: [] for a in ARMS}

    from sklearn.ensemble import RandomForestRegressor  # deferred to avoid top-level import cost

    for arm in ARMS:
        if arm in ("kuro_domain", "kuro_domain_centroid") and domain_arm_skip:
            continue  # leave finals[arm] empty when no domains available

        for seed in range(seeds):
            oracle = CombinatorialOracle.from_dict(raw, wt)
            rng = np.random.default_rng(1000 + seed)
            revealed: dict[str, float] = dict(oracle.reveal(r1))

            for _r in range(rounds):
                rev_ids = list(revealed)
                unrev = [i for i in pool_ids if i not in revealed]
                if not unrev or len(revealed) >= budget:
                    break

                Xtr = np.vstack([emb_np[i] for i in rev_ids])
                ytr = np.array([revealed[i] for i in rev_ids], dtype=float)
                Xun = np.vstack([emb_np[i] for i in unrev])

                m = RandomForestRegressor(**{**RF_KWARGS, "random_state": 1 + seed})
                m.fit(Xtr, ytr)
                mean, std, sample = combo_al_step(m, Xun, rng)
                k = min(batch, budget - len(revealed), len(unrev))

                if arm == "topn":
                    idx = select_indices("topn", mean=mean, std=std, sample=sample, n=k, rng=rng)
                    picks = [unrev[j] for j in idx]

                elif arm == "kuro_domain":
                    # rows: list[tuple[str, float]] sorted DESC by y_pred — as KURO expects.
                    rows: list[tuple[str, float]] = sorted(
                        [(unrev[j], float(mean[j])) for j in range(len(unrev))],
                        key=lambda x: -x[1],
                    )
                    # REAL call: first-position reduction applies (see module docstring).
                    selected_rows, _dom_stats = domain_aware_select(
                        rows, domains, top_n=k, ca_coords=ca
                    )
                    picks = [v for v, _ in selected_rows[:k]]

                elif arm == "kuro_pareto":
                    rows = sorted(
                        [(unrev[j], float(mean[j])) for j in range(len(unrev))],
                        key=lambda x: -x[1],
                    )
                    # REAL call: first-position reduction applies.
                    selected_rows, _replaced = pareto_diversity_select(
                        rows, top_n=k, ca_coords=ca
                    )
                    picks = [v for v, _ in selected_rows[:k]]

                elif arm == "embdiv":
                    anc = np.vstack([emb_np[i] for i in rev_ids])
                    idx = select_indices(
                        "embdiv", mean=mean, features=Xun, anchor_features=anc, n=k, rng=rng
                    )
                    picks = [unrev[j] for j in idx]

                elif arm == "kuro_ca":  # Ca-centroid maximin
                    feats = np.vstack([desc[desc_idx[i]] for i in unrev])
                    anc = np.vstack([desc[desc_idx[i]] for i in rev_ids])
                    idx = select_indices(
                        "embdiv", mean=mean, features=feats, anchor_features=anc, n=k, rng=rng
                    )
                    picks = [unrev[j] for j in idx]

                elif arm == "kuro_domain_centroid":
                    # Centroid-fixed: all substituted positions used for domain binning.
                    rows_c: list[tuple[str, float]] = sorted(
                        [(unrev[j], float(mean[j])) for j in range(len(unrev))],
                        key=lambda x: -x[1],
                    )
                    selected_rows_c, _dom_stats_c = domain_aware_select(
                        rows_c, domains, top_n=k, ca_coords=ca, position_mode="centroid"
                    )
                    picks = [v for v, _ in selected_rows_c[:k]]

                elif arm == "kuro_pareto_centroid":
                    # Centroid-fixed: all substituted positions used for diversity distance.
                    rows_pc: list[tuple[str, float]] = sorted(
                        [(unrev[j], float(mean[j])) for j in range(len(unrev))],
                        key=lambda x: -x[1],
                    )
                    selected_rows_pc, _replaced_pc = pareto_diversity_select(
                        rows_pc, top_n=k, ca_coords=ca, position_mode="centroid"
                    )
                    picks = [v for v, _ in selected_rows_pc[:k]]

                elif arm == "ucb":
                    idx = select_indices("ucb", mean=mean, std=std, n=k, rng=rng)
                    picks = [unrev[j] for j in idx]

                elif arm == "kuro_struct":
                    # Full-pool Ca-centroid maximin anchored on revealed history.
                    rows_s: list[tuple[str, float]] = [
                        (unrev[j], float(mean[j])) for j in range(len(unrev))
                    ]
                    selected_rows_s, _replaced_s = structural_diversity_select(
                        rows_s, k, ca_coords=ca, anchor_variants=list(revealed), kappa=0.0
                    )
                    picks = [v for v, _ in selected_rows_s]

                else:  # kuro_struct_blend
                    rows_sb: list[tuple[str, float]] = [
                        (unrev[j], float(mean[j])) for j in range(len(unrev))
                    ]
                    selected_rows_sb, _replaced_sb = structural_diversity_select(
                        rows_sb, k, ca_coords=ca, anchor_variants=list(revealed), kappa=0.3
                    )
                    picks = [v for v, _ in selected_rows_sb]

                revealed.update(oracle.reveal(picks))

            finals[arm].append(max(revealed.values()))

    # ── Per-arm summary ──────────────────────────────────────────────────────
    per_arm_mean: dict[str, float | None] = {}
    per_arm_cvar: dict[str, float | None] = {}
    for a in ARMS:
        v = finals[a]
        per_arm_mean[a] = float(np.mean(v)) if v else None
        per_arm_cvar[a] = float(metrics.cvar(v, 0.20)) if v else None

    # ── 9-cell decisions ─────────────────────────────────────────────────────
    decisions: dict[str, dict] = {}
    topn_nb = finals["topn"]

    for cmp_arm in COMPARISON_ARMS:
        key = f"{cmp_arm}_vs_topn"
        arm_nb = finals[cmp_arm]

        if not arm_nb:
            decisions[key] = {
                "skipped": True,
                "reason": domains_error or "kuro_domain arm skipped (no domains)",
            }
            continue

        cmp = stats.paired_comparison(arm_nb, topn_nb, seed=0)
        mean_v = stats.mean_verdict(cmp)

        # CVaR bootstrap: diff = cvar(topn) - cvar(arm_a); positive -> topn tail better
        # tail_outcome convention: ci of (topn_cvar - arm_cvar).
        # TAIL-ADV means arm_a (KURO) has better worst-case (ci_hi < 0 -> topn worse).
        boot_rng = np.random.default_rng(0)
        aa = np.asarray(arm_nb)
        bb = np.asarray(topn_nb)
        idxs = np.arange(aa.size)
        diffs = np.array([
            metrics.cvar(bb[boot_rng.choice(idxs, size=idxs.size, replace=True)], 0.20)
            - metrics.cvar(aa[boot_rng.choice(idxs, size=idxs.size, replace=True)], 0.20)
            for _ in range(10_000)
        ])
        tail = stats.tail_outcome(
            float(np.percentile(diffs, 2.5)),
            float(np.percentile(diffs, 97.5)),
        )
        cell = stats.decision_cell(mean_v, tail)

        decisions[key] = {
            "median_delta": cmp["median_delta"],
            "cliffs_delta": cmp["cliffs_delta"],
            "wilcoxon_p": cmp["wilcoxon_p"],
            "mean_verdict": mean_v,
            "tail_outcome": tail,
            "decision_cell": cell,
        }


    # ── kuro_struct vs ucb (strongest alternative baseline) ──────────────────
    _ucb_nb = finals["ucb"]
    _ks_nb = finals["kuro_struct"]
    if _ks_nb and _ucb_nb:
        _cmp_ucb = stats.paired_comparison(_ks_nb, _ucb_nb, seed=0)
        _mv_ucb = stats.mean_verdict(_cmp_ucb)
        _boot_rng2 = np.random.default_rng(0)
        _aa2 = np.asarray(_ks_nb)
        _bb2 = np.asarray(_ucb_nb)
        _idxs2 = np.arange(_aa2.size)
        _diffs2 = np.array([
            metrics.cvar(_bb2[_boot_rng2.choice(_idxs2, size=_idxs2.size, replace=True)], 0.20)
            - metrics.cvar(_aa2[_boot_rng2.choice(_idxs2, size=_idxs2.size, replace=True)], 0.20)
            for _ in range(10_000)
        ])
        _tail2 = stats.tail_outcome(
            float(np.percentile(_diffs2, 2.5)),
            float(np.percentile(_diffs2, 97.5)),
        )
        decisions["kuro_struct_vs_ucb"] = {
            "median_delta": _cmp_ucb["median_delta"],
            "cliffs_delta": _cmp_ucb["cliffs_delta"],
            "wilcoxon_p": _cmp_ucb["wilcoxon_p"],
            "mean_verdict": _mv_ucb,
            "tail_outcome": _tail2,
            "decision_cell": stats.decision_cell(_mv_ucb, _tail2),
        }
    else:
        decisions["kuro_struct_vs_ucb"] = {
            "skipped": True,
            "reason": "one or both arms had no results",
        }

    wall = time.perf_counter() - t0
    return {
        "assay": Path(assay_csv).name,
        "accession": uniprot_acc,
        "pool_size": len(sub),
        "n_seed": n_seed,
        "batch": batch,
        "rounds": rounds,
        "seeds_run": seeds,
        "budget": budget,
        "ca_available": ca is not None,
        "ca_resolved": ca_resolved,
        "ca_error": ca_error,
        "domains_available": bool(domains),
        "domains_resolved": domains_resolved,
        "domains_error": domains_error,
        "domain_arm_skip": domain_arm_skip,
        "per_arm_norm_best_mean": per_arm_mean,
        "per_arm_cvar20": per_arm_cvar,
        "decisions": decisions,
        "first_position_reduction": FIRST_POSITION_REDUCTION_NOTE,
        "wall_seconds": wall,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Smoke test (synthetic, exits 0 without ESM-2)
# ──────────────────────────────────────────────────────────────────────────────

def _smoke_test() -> int:
    """Synthetic cheap validation that the KURO arm wiring compiles and runs."""
    import tempfile, os

    # Build a tiny synthetic DMS CSV.
    rows_data = []
    wt_seq = "MKLVD" * 20  # 100 aa WT
    import random
    random.seed(42)
    aas = list("ACDEFGHIKLMNPQRSTVWY")
    for i in range(1, 6):  # positions 1-5
        for aa in aas[:5]:
            mut_seq = list(wt_seq)
            mut_seq[i - 1] = aa
            rows_data.append({
                "mutant": f"{wt_seq[i-1]}{i}{aa}:{wt_seq[i]}{i+1}{aas[(i+1)%20]}",
                "mutated_sequence": "".join(mut_seq),
                "DMS_score": float(i + aas.index(aa) * 0.1),
            })

    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = os.path.join(tmpdir, "smoke_test.csv")
        import csv
        with open(csv_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["mutant", "mutated_sequence", "DMS_score"])
            w.writeheader()
            w.writerows(rows_data)

        # Build synthetic combos for the CSV (need real colon combos).
        combo_rows = []
        for i in range(1, 4):
            for j in range(i + 1, 5):
                aa1, aa2 = aas[i % 20], aas[j % 20]
                wt1, wt2 = wt_seq[i - 1], wt_seq[j - 1]
                mut_s = list(wt_seq)
                mut_s[i - 1] = aa1
                mut_s[j - 1] = aa2
                combo_rows.append({
                    "mutant": f"{wt1}{i}{aa1}:{wt2}{j}{aa2}",
                    "mutated_sequence": "".join(mut_s),
                    "DMS_score": float(i * 0.5 + j * 0.3),
                })

        with open(csv_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["mutant", "mutated_sequence", "DMS_score"])
            w.writeheader()
            w.writerows(combo_rows)

        # Verify that domain_aware_select and pareto_diversity_select can be called.
        synthetic_rows: list[tuple[str, float]] = [
            (f"A{i}C:D{i+2}E", float(10 - i)) for i in range(1, 11)
        ]
        domains = [{"name": "d1", "start": 1, "end": 5}, {"name": "d2", "start": 6, "end": 12}]
        sel, _ = domain_aware_select(synthetic_rows, domains, top_n=3)
        assert len(sel) <= 3, f"domain_aware_select returned {len(sel)} > 3"

        sel_cent, _ = domain_aware_select(synthetic_rows, domains, top_n=3, position_mode="centroid")
        assert len(sel_cent) <= 3, f"domain_aware_select centroid returned {len(sel_cent)} > 3"

        sel2, _ = pareto_diversity_select(synthetic_rows, top_n=3, ca_coords=None)
        assert len(sel2) <= 3, f"pareto_diversity_select returned {len(sel2)} > 3"

        sel2_cent, _ = pareto_diversity_select(synthetic_rows, top_n=3, ca_coords=None, position_mode="centroid")
        assert len(sel2_cent) <= 3, f"pareto_diversity_select centroid returned {len(sel2_cent)} > 3"

    print("[smoke] domain_aware_select OK, pareto_diversity_select OK (first+centroid)")

    # Also verify structural_diversity_select compiles and runs.
    sel_struct, _rep = structural_diversity_select(
        synthetic_rows[:6], top_n=3, ca_coords=None, anchor_variants=[synthetic_rows[0][0]]
    )
    assert len(sel_struct) <= 3, f"structural_diversity_select returned {len(sel_struct)} > 3"
    sel_blend, _ = structural_diversity_select(
        synthetic_rows[:6], top_n=3, ca_coords=None, kappa=0.3
    )
    assert len(sel_blend) <= 3, f"kuro_struct_blend returned {len(sel_blend)} > 3"

    print("[smoke] structural_diversity_select OK (kappa=0 + kappa=0.3)")
    return 0


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Combinatorial AL bench — real KURO domain_aware_select + pareto_diversity_select"
    )
    p.add_argument("--smoke", action="store_true", help="Synthetic quick smoke test; exits 0")
    p.add_argument("--assay", default=None, help="Path to DMS CSV (overrides default 3-assay run)")
    p.add_argument("--accession", default=None, help="UniProt accession for --assay")
    p.add_argument("--pool", type=int, default=400)
    p.add_argument("--n-seed", type=int, default=10)
    p.add_argument("--batch", type=int, default=10)
    p.add_argument("--rounds", type=int, default=4)
    p.add_argument("--seeds", type=int, default=50)
    p.add_argument(
        "--cache-dir",
        default=str(Path(__file__).resolve().parents[1] / "results" / "embeddings"),
    )
    p.add_argument(
        "--domain-cache-dir",
        default=str(Path(__file__).resolve().parents[1] / "results" / "domain_cache"),
    )
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument(
        "--out",
        default=str(Path(__file__).resolve().parents[1] / "results" / "qa" / "kuro_real" / "bench_struct.json"),
    )
    args = p.parse_args(argv)

    if args.smoke:
        return _smoke_test()

    if args.assay:
        if not args.accession:
            p.error("--accession required when --assay is given")
        assay_list = [{"name": Path(args.assay).stem, "csv": args.assay, "accession": args.accession}]
    else:
        assay_list = DEFAULT_ASSAYS

    results: dict[str, dict] = {}
    for entry in assay_list:
        print(f"[kuro_real_bench] running {entry['name']} (acc={entry['accession']}) ...")
        res = run_kuro_bench(
            assay_csv=entry["csv"],
            uniprot_acc=entry["accession"],
            pool=args.pool,
            n_seed=args.n_seed,
            batch=args.batch,
            rounds=args.rounds,
            seeds=args.seeds,
            cache_dir=args.cache_dir,
            domain_cache_dir=args.domain_cache_dir,
            model=args.model,
        )
        results[entry["name"]] = res
        print(f"  done in {res['wall_seconds']:.1f}s")
        for dec_key, dec in res["decisions"].items():
            if dec.get("skipped"):
                print(f"  {dec_key}: SKIPPED ({dec.get('reason', '')})")
            else:
                print(f"  {dec_key}: {dec['decision_cell']} (mean={dec['mean_verdict']}, tail={dec['tail_outcome']})")
        for arm, mean_nb in res["per_arm_norm_best_mean"].items():
            cvar_val = res["per_arm_cvar20"].get(arm)
            if mean_nb is not None:
                print(f"  {arm}: mean_nb={mean_nb:.4f}  cvar20={cvar_val:.4f}")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\n[kuro_real_bench] wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
