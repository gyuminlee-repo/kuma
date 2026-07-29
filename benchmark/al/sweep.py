"""Track-1 sweep runner (plan Phase 2), runnable at any scale.

For each assay: resolve real domains, compute cold-start (ESM-2 LLR) once, embed
once (cached), then run every (arm, seed) cell of the low-N AL campaign. Collect
per-cell metrics, then paired arm comparisons (domain vs Top-N control) per
stratum with Wilcoxon + Cliff's delta + bootstrap CI, and the single pivotal
headline rule. The 217-assay run is the same code with the full assay list (its
gating cost is the one-time per-assay ESM-2 embedding, cached to disk).

This is NOT a conclusion at small scale; it exercises the full statistical
pipeline and yields real per-assay/seed comparison data.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from al import arms as arms_mod
from al import metrics as metrics_mod
from al import stats as stats_mod
from al.coldstart import esm2_zero_shot_llr
from al.domains import classify_stratum, fetch_domains
from al.embed_cache import DEFAULT_MODEL, embed_variants
from al.loop import run_campaign
from al.run_al_simulation import load_assay


def run_assay_cells(
    csv_path: str | Path,
    cache_dir: str | Path,
    domain_cache: str | Path,
    uniprot_acc: str,
    *,
    n: int = 10,
    k: int = 5,
    seeds: list[int],
    model: str = DEFAULT_MODEL,
    max_variants: int | None = None,
    allow_network_domains: bool = False,
) -> list[dict]:
    """Run all (arm, seed) cells for one assay; return per-cell metric records."""
    data = load_assay(csv_path)
    variants = data["variants"]
    if max_variants is not None and len(variants) > max_variants:
        rng = np.random.default_rng(0)
        idx = sorted(rng.choice(len(variants), size=max_variants, replace=False))
        variants = [variants[i] for i in idx]
    oracle = {v: data["oracle"][v] for v in variants}
    seqs = {v: data["seqs"][v] for v in variants}

    domains = fetch_domains(uniprot_acc, domain_cache, allow_network=allow_network_domains)
    positions = [int("".join(c for c in v[1:-1])) for v in variants]
    stratum = classify_stratum(domains, positions)

    cold = esm2_zero_shot_llr(data["wt"], variants, model_name=model)
    emb = embed_variants(data["assay"], seqs, cache_dir, model_name=model)

    records: list[dict] = []
    for seed in seeds:
        for arm in arms_mod.ARMS:
            res = run_campaign(arm, variants, emb, oracle, cold, n=n, k_rounds=k,
                               domains=domains, seed=seed)
            m = metrics_mod.campaign_metrics(res.revealed_order, [r.selected for r in res.rounds], oracle)
            records.append({
                "assay": data["assay"], "uniprot": uniprot_acc, "stratum": stratum,
                "domain_count": len(domains), "n_variants": len(variants),
                "arm": arm, "seed": seed, "n": n, "k": k, **m,
            })
    return records


def paired_arm_comparison(
    df: pd.DataFrame, arm_a: str, arm_b: str, metric: str
) -> dict:
    """Paired comparison of arm_a vs arm_b on `metric`, paired by (assay, seed)."""
    a = df[df["arm"] == arm_a].set_index(["assay", "seed"])[metric]
    b = df[df["arm"] == arm_b].set_index(["assay", "seed"])[metric]
    common = a.index.intersection(b.index)
    av = a.loc[common].to_numpy(dtype=float)
    bv = b.loc[common].to_numpy(dtype=float)
    comp = stats_mod.paired_comparison(av, bv)
    comp.update({"arm_a": arm_a, "arm_b": arm_b, "metric": metric})
    return comp


def summarize(df: pd.DataFrame, metric: str = "recall@1.0pct") -> dict:
    """Per-stratum paired comparisons (domain arms vs Top-N) + pivotal headline."""
    out: dict = {"metric": metric, "strata": {}}
    for stratum, sub in df.groupby("stratum"):
        comps = {}
        for arm in ("domain_r1only", "domain_every", "pareto_r1only", "pareto_every", "random_r1"):
            if (sub["arm"] == arm).any():
                comps[f"{arm}_vs_topn"] = paired_arm_comparison(sub, arm, "topn", metric)
        out["strata"][str(stratum)] = comps
    # pivotal headline: multi-domain stratum, domain_r1only vs topn (Holm here = raw, single test)
    multi = df[df["stratum"] == "multi"]
    if len(multi):
        pivot = paired_arm_comparison(multi, "domain_r1only", "topn", metric)
        out["pivotal"] = stats_mod.pivotal_headline(pivot)
        out["pivotal"]["regime"] = "multi-domain, low-N, domain_r1only vs Top-N"
    else:
        out["pivotal"] = {"benefit": None, "verdict": "no multi-domain stratum in this sweep"}
    return out
