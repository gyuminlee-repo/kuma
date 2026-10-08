"""End-to-end AL-simulation orchestrator (Track-1).

Wires the harness on a real ProteinGym DMS assay:
  DMS csv -> single-sub filter -> derive WT -> cold-start signal (ESM-2 zero-shot
  LLR) -> ESM-2 35M embeddings (cached) -> run each arm's AL campaign with the
  REAL EVOLVEpro top_layer surrogate -> per-arm metrics (recall@budget etc.).

Oracle = true DMS_score; revealed ONLY for selected variants (loop enforces the
firewall). This module is the runnable pilot driver; the full 217-sweep + paired
stats live in later phases and reuse ``run_assay``.

CLI:
    python -m al.run_al_simulation --assay <csv> --n 10 --k 5 --seed 0 \
        --arms topn,random_r1,domain_r1only,domain_every --model esm2_t12_35M_UR50D
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import numpy as np
import pandas as pd

from al import arms as arms_mod
from al import metrics as metrics_mod
from al.coldstart import derive_wt_sequence, esm2_zero_shot_llr
from al.embed_cache import DEFAULT_MODEL, embed_variants
from al.loop import run_campaign

_SINGLE = re.compile(r"^[A-Z]\d+[A-Z]$")


def load_assay(csv_path: str | Path) -> dict:
    """Load a ProteinGym DMS csv; return single-sub variants, seqs, oracle, WT."""
    df = pd.read_csv(csv_path, usecols=lambda c: c in {"mutant", "mutated_sequence", "DMS_score"})
    df = df[df["mutant"].astype(str).str.match(_SINGLE)].copy()
    df = df.dropna(subset=["DMS_score"]).drop_duplicates(subset=["mutant"])
    variants = df["mutant"].astype(str).tolist()
    seqs = dict(zip(variants, df["mutated_sequence"].astype(str), strict=True))
    oracle = dict(zip(variants, df["DMS_score"].astype(float), strict=True))
    wt = derive_wt_sequence(variants[0], seqs[variants[0]])
    return {"variants": variants, "seqs": seqs, "oracle": oracle, "wt": wt,
            "assay": Path(csv_path).stem, "length": len(wt)}


def run_assay(
    csv_path: str | Path,
    cache_dir: str | Path,
    *,
    n: int = 10,
    k: int = 5,
    seed: int = 0,
    arms: tuple[str, ...] = arms_mod.ARMS,
    model: str = DEFAULT_MODEL,
    domains: list[dict] | None = None,
    max_variants: int | None = None,
) -> pd.DataFrame:
    """Run the requested arms on one assay; return a per-arm metrics DataFrame."""
    data = load_assay(csv_path)
    variants = data["variants"]
    if max_variants is not None and len(variants) > max_variants:
        # deterministic subsample for smoke/pilot speed (keeps oracle distribution-ish)
        rng = np.random.default_rng(0)
        idx = sorted(rng.choice(len(variants), size=max_variants, replace=False))
        variants = [variants[i] for i in idx]
    oracle = {v: data["oracle"][v] for v in variants}
    seqs = {v: data["seqs"][v] for v in variants}

    # Cold-start signal: ESM-2 zero-shot LLR (no oracle).
    cold = esm2_zero_shot_llr(data["wt"], variants, model_name=model)
    # Embeddings (real ESM-2 mean-pool, cached per assay).
    emb = embed_variants(data["assay"], seqs, cache_dir, model_name=model)

    # Single whole-protein domain fallback if none supplied (domain arms == ~top-N
    # on a single-domain protein; real multi-domain boundaries come from al.domains).
    if domains is None:
        domains = [{"name": "full", "start": 1, "end": data["length"]}]

    rows = []
    for arm in arms:
        res = run_campaign(arm, variants, emb, oracle, cold, n=n, k_rounds=k,
                           domains=domains, seed=seed)
        m = metrics_mod.campaign_metrics(
            res.revealed_order, [r.selected for r in res.rounds], oracle
        )
        rows.append({"assay": data["assay"], "arm": arm, "seed": seed,
                     "n": n, "k": k, "n_variants": len(variants), **m})
    return pd.DataFrame(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="AL-simulation Track-1 runner")
    ap.add_argument("--assay", required=True, help="ProteinGym DMS csv path")
    ap.add_argument("--cache-dir", default=str(Path(__file__).resolve().parents[1] / "results" / "embeddings"))
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--arms", default=",".join(arms_mod.ARMS))
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--max-variants", type=int, default=None, help="subsample for smoke/pilot")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    df = run_assay(
        args.assay, args.cache_dir, n=args.n, k=args.k, seed=args.seed,
        arms=tuple(args.arms.split(",")), model=args.model, max_variants=args.max_variants,
    )
    cols = ["assay", "arm", "n_variants", "recall@1.0pct", "recall@5.0pct",
            "recall_auc@5.0pct", "max_fitness", "rounds_to_90pct_recall@5.0pct"]
    print(df[[c for c in cols if c in df.columns]].to_string(index=False))
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(args.out, index=False)
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
