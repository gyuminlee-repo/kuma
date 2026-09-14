"""Check that documents quoting this campaign's counts agree with the artefacts.

Every count this campaign publishes used to be a hand-copied integer. The
conditions behind it lived in prose and nothing compared the sentence to the
measurement, so the same run ended up carrying several different numbers across
the manuscript, the figure caption and the meeting note.

This reads claims.json, recomputes each cited value from the artefact that
produced it, and requires the document to contain the resulting sentence
verbatim. It does not parse free prose: each claim carries the exact wording
with the number replaced by {value}, so a rewritten sentence is reported as
missing rather than silently passing.

Sources a claim can draw on:

  workbook:<VERDICT>      one of the eight VerdictClass classes, from the
                          release workbook
  workbook:n_scored       designed-variant wells in that workbook
  workbook:pass_pct       PASS share of those wells, one decimal
  workbook:wt_total_pass  PASS over all 96 wells, control included
  workbook:rep:<VERDICT>  the same reanalysis at the 288-record replicate layer
  workbook:rep:n          how many replicate records that layer holds
  cells:<round>:<ref>:<arm>   wells reproducing the designed variant, results.csv
  gap:<round>:<arm>       how many wells the amplicon reference gains over the CDS one

Exit status is 0 only when every claim is found as written.
"""
import ast
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "release_r2"))

import count_cells  # noqa: E402
import count_workbook  # noqa: E402
from verdict_vocab import CLASSES, guard_line, require_total  # noqa: E402

RESULTS_CSV = os.path.join(HERE, "results.csv")
CLAIMS = os.path.join(HERE, "claims.json")


def build_values(workbook=None, results=None):
    """Compute every citable value once, from the artefacts themselves.

    The two paths are arguments so the fixture runner can point this at a
    workbook whose right answers are known, rather than only at the release
    artefacts.
    """
    workbook = workbook or count_workbook.WORKBOOK
    results = results or RESULTS_CSV
    values = {}

    designed, wt, _meta = count_workbook.read(workbook)
    n = len(designed)
    values["workbook:n_scored"] = n
    for cls in CLASSES:
        values[f"workbook:{cls}"] = sum(1 for v in designed.values() if v == cls)
    # Every well must land in exactly one class. Without this, a verdict
    # outside the vocabulary would leave the table looking complete.
    require_total({c: values[f"workbook:{c}"] for c in CLASSES}, n,
                  "claims consolidated tally")
    npass = values["workbook:PASS"]
    values["workbook:pass_pct"] = f"{100.0 * npass / n:.1f}" if n else "n/a"
    values["workbook:wt_total_pass"] = npass + sum(
        1 for v in wt.values() if v == "PASS")

    # Replicate layer, the stratum the supplementary figure reports.
    wb = count_workbook.openpyxl.load_workbook(workbook, data_only=True)
    reps = count_workbook.read_replicates(wb)
    values["workbook:rep:n"] = len(reps)
    rep_counts = {}
    for _s, _w, _r, _m, verdict in reps:
        rep_counts[verdict] = rep_counts.get(verdict, 0) + 1
    for cls in CLASSES:
        values[f"workbook:rep:{cls}"] = rep_counts.get(cls, 0)
    require_total({c: values[f"workbook:rep:{c}"] for c in CLASSES}, len(reps),
                  "claims replicate tally")

    cells = count_cells.count(results)
    for (rnd, ref), per_arm in cells.items():
        per_arm = dict(per_arm)
        values[f"cells:{rnd}:{ref}:_n_scored"] = per_arm.pop("_n_scored")
        for arm, got in per_arm.items():
            values[f"cells:{rnd}:{ref}:{arm}"] = got

    # Derived gaps. The caption states the size of the reference effect as its
    # own number ("9 wells", "1 well"), and a reader who updates an endpoint
    # without recomputing the gap leaves a sentence that contradicts itself.
    for rnd in {r for r, _ in cells}:
        amp, cds = cells.get((rnd, "amplicon")), cells.get((rnd, "cds"))
        if not amp or not cds:
            continue
        for arm in amp:
            if arm != "_n_scored" and arm in cds:
                values[f"gap:{rnd}:{arm}"] = amp[arm] - cds[arm]
    return values


# The figure script holds the same twenty counts as python literals. They are
# read with ast rather than a regex, so a renamed variable or a changed shape is
# reported instead of being matched by accident.
FIGURE_SCRIPT = ("$OBSIDIAN_VAULT/010.KRIBB/040.Weekly/assets/_scripts/"
                 "mame_method_fig.py")
FIGURE_PANELS = {"PANEL_A_R31": "R3-1", "PANEL_A_R2": "R2"}
N_LABEL_RE = re.compile(r"^n = (\d+) scored wells$")


def check_figure_script(values, path):
    """Compare the figure's literals with the counts results.csv yields.

    Panel B is deliberately not checked. Its numbers count wells the methods
    disagree on rather than wells a method failed, and that is not a quantity
    count_cells computes, so claiming to check it would be worse than saying so.
    """
    reports, fails = [], []
    if not os.path.isfile(path):
        return [], [f"figure script not found at {path}"]
    tree = ast.parse(open(path, encoding="utf-8").read())
    found = {}
    n_labels = []
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        if target.id in FIGURE_PANELS:
            try:
                found[target.id] = ast.literal_eval(node.value)
            except ValueError:
                fails.append(f"{target.id} is no longer a plain literal")
        elif target.id == "PANEL_A_ROUNDS":
            for sub in ast.walk(node.value):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                    m = N_LABEL_RE.match(sub.value)
                    if m:
                        n_labels.append(int(m.group(1)))

    arm_of = {label: arm for arm, label in count_cells.LABEL.items()}
    for var, rnd in FIGURE_PANELS.items():
        if var not in found:
            fails.append(f"{var} not found in the figure script")
            continue
        for label, pair in found[var].items():
            arm = arm_of.get(label)
            if arm is None:
                fails.append(f"{var}: method label '{label}' is not a known arm")
                continue
            if not (isinstance(pair, tuple) and len(pair) == 2):
                fails.append(f"{var}[{label}] is not a (cds, amplicon) pair")
                continue
            for got, ref in zip(pair, ("cds", "amplicon")):
                key = f"cells:{rnd}:{ref}:{arm}"
                want = values.get(key)
                reports.append(key)
                if got != want:
                    fails.append(f"figure {var}[{label}] {ref}: draws {got}, "
                                 f"results.csv gives {want}")

    wanted_n = [values.get(f"cells:{FIGURE_PANELS[v]}:amplicon:_n_scored")
                for v in ("PANEL_A_R31", "PANEL_A_R2")]
    reports.extend(["n_scored:R3-1", "n_scored:R2"])
    if n_labels != wanted_n:
        fails.append(f"figure panel A denominators {n_labels} != {wanted_n}")
    return reports, fails


def variant_scan(quote, want, text):
    """Find copies of this sentence that carry some other number.

    A distribution sentence is repeated across the body, the caption and the
    working notes. Correcting one copy and not the rest is the failure this
    catches, so the template is turned into a pattern over the literal wording
    with only the value position left open. Nothing here reads free prose.
    """
    before, after = quote.split("{value}")
    # A comma is a thousands separator only between digit groups, never a
    # trailing one: "NO_CALL 3, LOWDEPTH" must yield 3 and not "3,".
    number = r"([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]+)?)"
    pattern = re.escape(before) + number + re.escape(after)
    found = [m.group(1) for m in re.finditer(pattern, text)]
    return [g for g in found if g != want], len(found)


def resolve(path):
    """Documents are addressed through the vault variable, never a fixed path."""
    return os.path.expandvars(path)


def main():
    claims = json.load(open(CLAIMS, encoding="utf-8"))
    values = build_values()

    checked, fails = 0, []
    cache = {}
    for c in claims:
        checked += 1
        cid, src = c["id"], c["source"]
        if src not in values:
            fails.append(f"{cid}: source '{src}' is not one this script can compute")
            continue
        want = str(values[src])
        sentence = c["quote"].replace("{value}", want)
        doc = resolve(c["doc"])
        if doc not in cache:
            if not os.path.isfile(doc):
                cache[doc] = None
            else:
                cache[doc] = open(doc, encoding="utf-8").read()
        text = cache[doc]
        if text is None:
            fails.append(f"{cid}: document not found at {doc}")
            continue
        if sentence in text:
            if c.get("mode") == "all":
                wrong, total = variant_scan(c["quote"], want, text)
                if wrong:
                    fails.append(f"{cid}: {total} copies of this sentence, "
                                 f"{len(wrong)} carry {sorted(set(wrong))} "
                                 f"instead of {want}")
                    continue
                print(f"  ok    {cid:34s} {src} = {want}  "
                      f"({total} copies agree)")
            else:
                print(f"  ok    {cid:34s} {src} = {want}")
            continue
        # Say what the document holds instead, so the report is actionable.
        head = c["quote"].split("{value}")[0][-40:]
        hint = ""
        for line in text.splitlines():
            if head and head in line:
                hint = f"\n          document says: {line.strip()[:160]}"
                break
        fails.append(f"{cid}: expected {src} = {want}, wording not found in "
                     f"{os.path.basename(doc)}{hint}")

    fig_path = resolve(FIGURE_SCRIPT)
    fig_reports, fig_fails = check_figure_script(values, fig_path)
    for key in fig_reports:
        print(f"  ok    {'figure literal':34s} {key}"
              if not fig_fails else f"  ..    figure literal {key}")
    checked += len(fig_reports)
    fails.extend(fig_fails)

    for f in fails:
        print(f"  FAIL  {f}")
    print(f"\nclaims checked: {checked}, mismatches: {len(fails)}")
    print(guard_line(__file__))
    print("LIMIT: only the claims listed in claims.json and the figure panel A "
          "literals are checked. A number added to a document without a claim "
          "entry is not covered, and figure panel B counts method disagreement "
          "rather than failure so it is not derived here.")
    print("CLAIMS_OK" if checked and not fails else "CLAIMS_FAIL")
    return 0 if checked and not fails else 1


if __name__ == "__main__":
    sys.exit(main())
