"""Small EVOLVEpro execution adapter used by the GUI sidecar.

The upstream EVOLVEpro package exposes Python APIs but no console entry point.
This adapter keeps the GUI executable without vendoring EVOLVEpro: it runs
inside the user's conda environment and imports their installed package.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from Bio import SeqIO

# Dual-context import: adapter.py is executed both as a __main__ script
# (conda subprocess, __package__ is None) and as a package module (tests).
if not __package__:
    import embedding_cache  # type: ignore[import]
else:
    from . import embedding_cache

AA_LIST = list("ACDEFGHIKLMNPQRSTVWY")
AA_ALLOWED = set("ACDEFGHIKLMNPQRSTVWYXBZUO")
NT_ALLOWED = set("ACGTUN")
FULL_VARIANT_RE = re.compile(r"^([ACDEFGHIKLMNPQRSTVWY])(\d+)([ACDEFGHIKLMNPQRSTVWY])$")
SHORT_VARIANT_RE = re.compile(r"^(\d+)([ACDEFGHIKLMNPQRSTVWY])$")


def _read_input(path: Path) -> pd.DataFrame:
	if path.suffix.lower() in {".xlsx", ".xls"}:
		return pd.read_excel(path)
	return pd.read_csv(path)


def _normalize_variant(raw_variant: object, wt_sequence: str) -> str:
	variant = str(raw_variant).strip()
	if variant == "WT":
		return "WT"
	if match := FULL_VARIANT_RE.match(variant):
		position = int(match.group(2))
		if position < 1 or position > len(wt_sequence):
			raise ValueError(f"variant position out of WT range: {variant}")
		return variant
	if match := SHORT_VARIANT_RE.match(variant):
		position = int(match.group(1))
		mutated_aa = match.group(2)
		if position < 1 or position > len(wt_sequence):
			raise ValueError(f"variant position out of WT range: {variant}")
		return f"{wt_sequence[position - 1]}{position}{mutated_aa}"
	raise ValueError(f"unsupported variant notation: {variant}")


def _single_mutant_index(wt_sequence: str) -> list[str]:
	variants = ["WT"]
	for i, wt_aa in enumerate(wt_sequence, start=1):
		if wt_aa not in AA_LIST:
			continue
		for aa in AA_LIST:
			if aa != wt_aa:
				variants.append(f"{wt_aa}{i}{aa}")
	return variants


def _fallback_embeddings(variants: list[str], wt_sequence: str) -> pd.DataFrame:
	"""Create deterministic lightweight features when no embedding CSV is supplied."""
	aa_to_idx = {aa: i for i, aa in enumerate(AA_LIST)}
	rows = []
	for variant in variants:
		features = np.zeros(43, dtype=float)
		if variant == "WT":
			rows.append(features)
			continue
		match = FULL_VARIANT_RE.match(variant)
		if match is None:
			rows.append(features)
			continue
		wt_aa, position_raw, mut_aa = match.groups()
		position = int(position_raw)
		features[0] = position / max(len(wt_sequence), 1)
		features[1 + aa_to_idx[wt_aa]] = 1.0
		features[21 + aa_to_idx[mut_aa]] = 1.0
		features[41] = abs(aa_to_idx[mut_aa] - aa_to_idx[wt_aa]) / (len(AA_LIST) - 1)
		features[42] = 1.0 if position <= len(wt_sequence) / 2 else 0.0
		rows.append(features)
	return pd.DataFrame(rows, index=variants)


def _mutate_sequence(wt_sequence: str, variant: str) -> str:
	"""Apply a single amino-acid substitution (e.g. 'A12V') to the WT sequence."""
	if variant == "WT":
		return wt_sequence
	match = FULL_VARIANT_RE.match(variant)
	if match is None:
		raise ValueError(f"cannot apply variant to WT: {variant}")
	wt_aa, position_raw, mut_aa = match.groups()
	position = int(position_raw)
	if position < 1 or position > len(wt_sequence):
		raise ValueError(f"variant position out of WT range: {variant}")
	if wt_sequence[position - 1] != wt_aa:
		raise ValueError(
			f"variant WT residue mismatch: {variant} expects {wt_aa} at {position}, "
			f"got {wt_sequence[position - 1]}"
		)
	return wt_sequence[: position - 1] + mut_aa + wt_sequence[position:]


def load_esm2_model(model_id: str):
	"""Load a pretrained ESM-2 model via fair-esm.

	model_id is the full fair-esm name (e.g. ``esm2_t33_650M_UR50D``).
	"""
	import esm  # fair-esm
	import torch

	print(f"loading ESM-2 model: {model_id}", flush=True)  # noqa: T201
	print("(first download may take 30s to several minutes)", flush=True)  # noqa: T201
	model, alphabet = esm.pretrained.load_model_and_alphabet(model_id)
	# Switch to inference mode (disable dropout); fair-esm requires this.
	model.train(False)
	device_str = "cuda" if torch.cuda.is_available() else "cpu"
	if device_str == "cuda":
		model = model.cuda()
	print(f"ESM-2 model ready on {device_str}", flush=True)  # noqa: T201
	return model, alphabet, device_str


def extract_esm2_embeddings(
	model,
	alphabet,
	sequences: list[tuple[str, str]],
	device_str: str,
	toks_per_batch: int = 4096,
	truncation_seq_length: int = 1022,
) -> tuple[dict[str, np.ndarray], float]:
	"""Extract per-residue ESM-2 representations from the final layer.

	Returns a tuple of:
	  - ``{label: ndarray of shape (T, D)}`` where ``T`` is the (truncated)
	    sequence length and ``D`` the model embedding dimension.
	  - Measured throughput in tokens/sec (0.0 when no batches were processed).
	"""
	import torch

	batch_converter = alphabet.get_batch_converter()
	repr_layer = model.num_layers

	# Simple chunking so very large sequence sets do not OOM. The token budget
	# upstream uses extra_toks_per_seq=1 so we approximate with seq len + 2.
	chunks: list[list[tuple[str, str]]] = []
	current: list[tuple[str, str]] = []
	current_tokens = 0
	for label, seq in sequences:
		seq_tokens = min(len(seq), truncation_seq_length) + 2
		if current and current_tokens + seq_tokens > toks_per_batch:
			chunks.append(current)
			current = []
			current_tokens = 0
		current.append((label, seq))
		current_tokens += seq_tokens
	if current:
		chunks.append(current)

	# Pre-compute total tokens across all chunks for ETA denominator.
	total_tokens = sum(
		sum(min(len(seq), truncation_seq_length) + 2 for _, seq in chunk)
		for chunk in chunks
	)

	msg = f"extracting ESM-2 embeddings for {len(sequences)} sequences (layer {repr_layer}, {len(chunks)} batches)"
	print(msg, flush=True)  # noqa: T201

	out: dict[str, np.ndarray] = {}
	cumulative_tokens = 0
	tok_per_sec = 0.0
	t0 = time.perf_counter()
	for chunk_idx, chunk in enumerate(chunks, start=1):
		# Truncate sequences before tokenization to respect ESM context limit.
		truncated = [(lbl, seq[:truncation_seq_length]) for lbl, seq in chunk]
		labels, _strs, tokens = batch_converter(truncated)
		if device_str == "cuda":
			tokens = tokens.cuda()
		with torch.no_grad():
			results = model(tokens, repr_layers=[repr_layer], return_contacts=False)
		representations = results["representations"][repr_layer].cpu().numpy()
		for i, (label, seq) in enumerate(truncated):
			seq_len = len(seq)
			out[label] = representations[i, 1 : 1 + seq_len, :]
		batch_tokens = sum(min(len(seq), truncation_seq_length) + 2 for _, seq in truncated)
		cumulative_tokens += batch_tokens
		elapsed = time.perf_counter() - t0
		if elapsed > 0:
			tok_per_sec = cumulative_tokens / elapsed
			remaining_tokens = max(0, total_tokens - cumulative_tokens)
			remaining_seconds = remaining_tokens / tok_per_sec if tok_per_sec > 0 else 0.0
			print(f"throughput: {tok_per_sec:.1f} tok/s", flush=True)  # noqa: T201
			print(f"eta: {remaining_seconds:.0f} s", flush=True)  # noqa: T201
		batch_msg = f"  batch {chunk_idx}/{len(chunks)} done ({len(chunk)} seqs)"
		print(batch_msg, flush=True)  # noqa: T201

	if out:
		any_label = next(iter(out))
		done_msg = f"ESM-2 embeddings extracted (dim={out[any_label].shape[-1]})"
		print(done_msg, flush=True)  # noqa: T201
	return out, tok_per_sec


def _esm2_variant_embeddings(
	variants: list[str], wt_sequence: str, model_id: str
) -> tuple[pd.DataFrame, float]:
	"""Run ESM-2 over WT + single-mutant variants and mean-pool per sequence.

	Returns a tuple of:
	  - DataFrame indexed by variant label with one row per variant (mean-pooled).
	  - Measured throughput in tokens/sec from extract_esm2_embeddings.
	"""
	sequences: list[tuple[str, str]] = []
	for variant in variants:
		sequences.append((variant, _mutate_sequence(wt_sequence, variant)))

	model, alphabet, device_str = load_esm2_model(model_id)
	emb_dict, final_tok_per_sec = extract_esm2_embeddings(model, alphabet, sequences, device_str)

	rows: list[np.ndarray] = []
	index: list[str] = []
	for variant in variants:
		per_residue = emb_dict[variant]
		rows.append(per_residue.mean(axis=0))
		index.append(variant)
	return pd.DataFrame(np.vstack(rows), index=index), final_tok_per_sec


def _load_embeddings(
	path: str | None,
	wt_sequence: str,
	model_id: str | None = None,
	cache_dir: str | None = None,
) -> pd.DataFrame:
	"""Load embeddings with priority: explicit CSV > disk cache > on-the-fly > fallback.

	Args:
		path: Explicit embeddings CSV path (highest priority).
		wt_sequence: Wild-type amino acid sequence.
		model_id: ESM-2 model identifier; required for cache lookup and on-the-fly.
		cache_dir: Path string to embedding cache directory. None disables caching.
	"""
	if path:
		embeddings = pd.read_csv(path, index_col=0)
		return embeddings.sort_index()

	# Disk cache: only meaningful when model_id is known (cache key requires it).
	if cache_dir and model_id and embedding_cache.is_cached(Path(cache_dir), wt_sequence, model_id):
		cache_msg = f"loading embeddings from disk cache: {cache_dir}"
		print(cache_msg, flush=True)  # noqa: T201
		return embedding_cache.load_cached(Path(cache_dir), wt_sequence, model_id).sort_index()

	variants = _single_mutant_index(wt_sequence)
	if model_id:
		try:
			df, final_tok_per_sec = _esm2_variant_embeddings(variants, wt_sequence, model_id)
			if cache_dir and final_tok_per_sec > 0:
				embedding_cache.save_embeddings(df, Path(cache_dir), wt_sequence, model_id)
				import torch  # only needed for gpu_flag on actual ESM-2 run
				gpu_flag = torch.cuda.is_available()
				embedding_cache.write_throughput(
					Path(cache_dir),
					embedding_cache.machine_fingerprint(),
					model_id,
					final_tok_per_sec,
					gpu_flag,
				)
			return df.sort_index()
		except ImportError as exc:
			warn_msg = f"fair-esm not available ({exc}); falling back to deterministic features"
			print(warn_msg, flush=True)  # noqa: T201
	return _fallback_embeddings(variants, wt_sequence).sort_index()


def _build_labels(measured: pd.DataFrame, embeddings_index: pd.Index) -> tuple[pd.DataFrame, pd.DataFrame]:
	labels = pd.DataFrame({"variant": embeddings_index.astype(str)})
	labels["activity"] = np.nan
	labels["iteration"] = np.nan

	measured = measured.copy()
	if "iteration" not in measured.columns:
		measured["iteration"] = measured["variant"].apply(lambda v: 0.0 if v == "WT" else 1.0)
	activity_min = measured["activity"].min()
	activity_max = measured["activity"].max()
	if activity_max == activity_min:
		measured["activity_scaled"] = 1.0
	else:
		measured["activity_scaled"] = (measured["activity"] - activity_min) / (activity_max - activity_min)
	measured["activity_binary"] = measured["activity"].apply(lambda x: 1 if x >= 1 else 0)

	labels = labels.merge(
		measured[["variant", "activity", "iteration", "activity_scaled", "activity_binary"]],
		on="variant",
		how="left",
		suffixes=("", "_measured"),
	)
	for col in ["activity", "iteration"]:
		labels[col] = labels[f"{col}_measured"].combine_first(labels[col])
		labels = labels.drop(columns=[f"{col}_measured"])
	labels["activity_scaled"] = labels["activity_scaled"]
	labels["activity_binary"] = labels["activity_binary"]
	iteration = measured[["variant", "iteration"]].copy()
	return iteration, labels


def _load_round_data(input_paths: list[Path], wt_sequence: str) -> tuple[pd.DataFrame, pd.DataFrame]:
	frames: list[pd.DataFrame] = []
	manifest_rows: list[dict[str, object]] = []
	for round_number, input_path in enumerate(input_paths, start=1):
		input_df = _read_input(input_path)
		required = {"Variant", "activity"}
		missing_columns = required - set(input_df.columns)
		if missing_columns:
			raise ValueError(
				f"round {round_number} input is missing required columns: {sorted(missing_columns)}"
			)
		measured = input_df[["Variant", "activity"]].copy()
		measured["variant"] = measured["Variant"].apply(lambda v: _normalize_variant(v, wt_sequence))
		measured["activity"] = pd.to_numeric(measured["activity"], errors="raise")
		measured["round"] = round_number
		measured["iteration"] = measured["variant"].apply(
			lambda v: 0.0 if v == "WT" else float(round_number)
		)
		frames.append(measured[["variant", "activity", "round", "iteration"]])
		manifest_rows.append(
			{"round": round_number, "path": str(input_path), "rows": len(measured)}
		)
	if not frames:
		raise ValueError("at least one --round-file or --input is required")
	combined = pd.concat(frames, ignore_index=True)
	duplicates = combined.loc[combined["variant"].duplicated(keep=False), ["variant", "round"]]
	if not duplicates.empty:
		duplicate_variants = sorted(duplicates["variant"].unique().tolist())
		raise ValueError(
			"duplicate variants across round files after normalization: "
			f"{duplicate_variants[:10]}"
		)
	return combined, pd.DataFrame(manifest_rows)


def _read_wt_sequence(wt_sequence: str | None, wt_fasta: str | None) -> str:
	if wt_fasta:
		sequence = str(SeqIO.read(wt_fasta, "fasta").seq).strip().upper()
		return _validate_wt_protein_sequence(sequence, f"WT FASTA {wt_fasta}")
	if wt_sequence:
		return _validate_wt_protein_sequence(wt_sequence.strip().upper(), "WT sequence")
	raise ValueError("either --wt-sequence or --wt-fasta is required")


def _validate_wt_protein_sequence(sequence: str, source: str) -> str:
	sequence = re.sub(r"\s+", "", sequence).upper().rstrip("*")
	if not sequence:
		raise ValueError(f"{source} is empty. EVOLVEpro requires a protein FASTA amino acid sequence.")

	chars = set(sequence)
	invalid = chars - AA_ALLOWED
	if invalid:
		raise ValueError(
			f"{source} contains invalid amino acid characters: {''.join(sorted(invalid))}. "
			"EVOLVEpro requires a protein FASTA, not nucleotide/DNA/RNA sequence."
		)
	if len(sequence) >= 10 and chars <= NT_ALLOWED:
		raise ValueError(
			f"{source} looks like a nucleotide/DNA/RNA sequence. "
			"EVOLVEpro and ESM-2 require a protein FASTA with amino acid letters "
			"(for example MKT...). Translate CDS/NT sequence to protein before running."
		)
	return sequence


def run(
	input_paths: list[Path],
	wt_sequence: str,
	output_dir: Path,
	top_n: int,
	embeddings_csv: str | None,
	model_id: str | None = None,
	n_rounds: int = 1,
	embeddings_cache_dir: str | None = None,
) -> None:
	evolvepro_repo_path = os.environ.get("EVOLVEPRO_REPO_PATH")
	if evolvepro_repo_path:
		sys.path.insert(0, evolvepro_repo_path)

	from evolvepro.src.model import top_layer

	# Emit round markers consumed by sidecar/runner.py:_RE_ROUND so the GUI
	# progress bar advances. EVOLVEpro top_layer is a single-shot call here,
	# so "rounds" reflects phase completion against the runner's expected
	# n_rounds (passed via --rounds so the denominator matches the GUI).
	total_rounds = max(n_rounds, 1)
	print(f"round 0/{total_rounds}", flush=True)  # noqa: T201
	print("loading input", flush=True)  # noqa: T201
	measured, manifest = _load_round_data(input_paths, wt_sequence)

	print("loading embeddings", flush=True)  # noqa: T201
	embeddings = _load_embeddings(embeddings_csv, wt_sequence, model_id, embeddings_cache_dir)
	missing = sorted(set(measured["variant"]) - set(embeddings.index.astype(str)))
	if missing:
		raise ValueError(f"measured variants missing from embeddings: {missing[:10]}")

	print(f"round {total_rounds}/{total_rounds}", flush=True)  # noqa: T201
	print("scoring variants", flush=True)  # noqa: T201
	iteration, labels = _build_labels(
		measured[["variant", "activity", "iteration"]], embeddings.index
	)
	this_round_variants, df_test, df_sorted_all = top_layer(
		iter_train=iteration["iteration"].unique().tolist(),
		iter_test=None,
		embeddings_pd=embeddings,
		labels_pd=labels,
		measured_var="activity",
		regression_type="randomforest",
		experimental=True,
	)

	output_dir.mkdir(parents=True, exist_ok=True)
	manifest.to_csv(output_dir / "round_data_manifest.csv", index=False)
	iteration.to_csv(output_dir / "iteration.csv", index=False)
	this_round_variants.to_csv(output_dir / "this_round_variants.csv", index=False)
	df_test = df_test.sort_values("y_pred", ascending=False)
	df_test.to_csv(output_dir / "df_test.csv", index=False)
	df_sorted_all.to_csv(output_dir / "df_sorted_all.csv", index=False)

	top = df_test.copy() if top_n <= 0 else df_test.head(top_n).copy()
	top.insert(0, "rank", range(1, len(top) + 1))
	top.rename(columns={"y_pred": "y_predicted"}, inplace=True)
	top.to_csv(output_dir / "top_variants.csv", index=False)
	print(f"done: {output_dir / 'df_test.csv'}", flush=True)  # noqa: T201


_ESM2_CHOICES = (
	"esm2_t6_8M_UR50D",
	"esm2_t12_35M_UR50D",
	"esm2_t30_150M_UR50D",
	"esm2_t33_650M_UR50D",
	"esm2_t36_3B_UR50D",
	"esm2_t48_15B_UR50D",
)


def main() -> None:
	parser = argparse.ArgumentParser(description="Run EVOLVEpro scoring for GUI.")
	parser.add_argument("--input", default=None)
	parser.add_argument("--round-file", action="append", default=[])
	parser.add_argument("--wt-sequence", default=None)
	parser.add_argument("--wt-fasta", default=None)
	parser.add_argument("--rounds", type=int, default=1)
	parser.add_argument("--output-dir", required=True)
	parser.add_argument("--top-n", type=int, default=20)
	parser.add_argument("--embeddings-csv", default=None)
	parser.add_argument(
		"--embeddings-cache-dir",
		default=None,
		help="Directory for disk-cached ESM-2 embeddings. Omit to disable caching.",
	)
	parser.add_argument(
		"--model-id",
		choices=_ESM2_CHOICES,
		default="esm2_t33_650M_UR50D",
		help="ESM2 model variant to use for embeddings (loaded via fair-esm when no --embeddings-csv is provided).",
	)
	args = parser.parse_args()
	print(f"adapter start: esm2_model_id={args.model_id}", flush=True)  # noqa: T201
	wt_sequence = _read_wt_sequence(args.wt_sequence, args.wt_fasta)
	print(f"validated WT protein sequence: {len(wt_sequence)} aa", flush=True)  # noqa: T201
	input_paths = [Path(p) for p in args.round_file]
	if not input_paths and args.input:
		input_paths = [Path(args.input)]
	print(f"round files: {len(input_paths)}", flush=True)  # noqa: T201
	run(
		input_paths=input_paths,
		wt_sequence=wt_sequence,
		output_dir=Path(args.output_dir),
		top_n=args.top_n,
		embeddings_csv=args.embeddings_csv,
		model_id=args.model_id,
		n_rounds=args.rounds,
		embeddings_cache_dir=args.embeddings_cache_dir,
	)


if __name__ == "__main__":
	main()
