"""Assert the three pre-existing (round,reference) cells are byte-identical
row lists in file order, before vs after regeneration. Counts alone would miss
a reordering or a changed field, so this compares the full row dicts."""
import csv, sys
before, after = sys.argv[1], sys.argv[2]
KEYS = [("R2", "amplicon", 477), ("R2", "cds", 478), ("R3-1", "amplicon", 477)]

def load(p):
    return list(csv.DictReader(open(p)))

b, a = load(before), load(after)
ok = True
for rnd, ref, want_n in KEYS:
    bs = [r for r in b if r["round"] == rnd and r["reference"] == ref]
    as_ = [r for r in a if r["round"] == rnd and r["reference"] == ref]
    same = bs == as_
    print(f"({rnd},{ref}): before={len(bs)} after={len(as_)} expected={want_n} "
          f"rows_identical={same}")
    if len(as_) != want_n or not same:
        ok = False
        for i, (x, y) in enumerate(zip(bs, as_)):
            if x != y:
                print(f"  first diff at index {i}:\n   before={x}\n   after ={y}")
                break
new = [r for r in a if (r["round"], r["reference"]) == ("R3-1", "cds")]
print(f"(R3-1,cds): new rows={len(new)}")
print(f"total before={len(b)} after={len(a)}")
print("INVARIANCE_OK" if ok else "INVARIANCE_FAIL")
sys.exit(0 if ok else 1)
