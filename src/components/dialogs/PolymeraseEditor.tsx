import { useEffect, useState } from "react";

import type { PolymeraseProfile } from "../../types/models";
import { Button } from "../ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import { Input } from "../ui/input";

const DEFAULT_PROFILE: PolymeraseProfile = {
  name: "",
  tm_method: "santalucia",
  salt_correction: "owczarzy",
  opt_tm: 62,
  min_tm: 55,
  max_tm: 65,
  opt_size: 22,
  min_size: 18,
  max_size: 30,
  min_gc: 40,
  max_gc: 60,
  salt_monovalent: 50,
  salt_divalent: 2,
  dntp_conc: 0.8,
  dna_conc: 250,
  max_tm_diff: 4,
  opt_tm_fwd: 62,
  opt_tm_rev: 58,
  opt_tm_overlap: 42,
  min_3prime_dist: 0,
};

interface PolymeraseEditorProps {
  open: boolean;
  profile?: PolymeraseProfile | null;
  onOpenChange: (open: boolean) => void;
  onSave: (profile: PolymeraseProfile) => Promise<void>;
}

type OptionalNumericPolymeraseKey =
  | "opt_tm_fwd"
  | "opt_tm_rev"
  | "opt_tm_overlap"
  | "min_3prime_dist"
  | "overlap_len"
  | "fwd_len_min"
  | "fwd_len_max"
  | "rev_len_min"
  | "rev_len_max";

type RequiredNumericPolymeraseKey = Exclude<
  keyof PolymeraseProfile,
  "name" | "tm_method" | "salt_correction" | "default_overlap_mode" | OptionalNumericPolymeraseKey
>;

type NumericPolymeraseKey =
  | RequiredNumericPolymeraseKey
  | OptionalNumericPolymeraseKey;

function isOptionalNumericPolymeraseKey(
  key: NumericPolymeraseKey,
): key is OptionalNumericPolymeraseKey {
  return (
    key === "opt_tm_fwd" ||
    key === "opt_tm_rev" ||
    key === "opt_tm_overlap" ||
    key === "min_3prime_dist" ||
    key === "overlap_len" ||
    key === "fwd_len_min" ||
    key === "fwd_len_max" ||
    key === "rev_len_min" ||
    key === "rev_len_max"
  );
}

function parsePolymeraseNumber<K extends RequiredNumericPolymeraseKey>(
  key: K,
  raw: string,
): PolymeraseProfile[K];
function parsePolymeraseNumber<K extends OptionalNumericPolymeraseKey>(
  key: K,
  raw: string,
): PolymeraseProfile[K];
function parsePolymeraseNumber(key: NumericPolymeraseKey, raw: string) {
  if (raw === "") {
    if (isOptionalNumericPolymeraseKey(key)) {
      return undefined;
    }
    return DEFAULT_PROFILE[key];
  }
  return Number(raw);
}

export function PolymeraseEditor({
  open,
  profile,
  onOpenChange,
  onSave,
}: PolymeraseEditorProps) {
  const [form, setForm] = useState<PolymeraseProfile>(profile ?? DEFAULT_PROFILE);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setForm(profile ?? DEFAULT_PROFILE);
    setError("");
  }, [profile, open]);

  const update = <K extends keyof PolymeraseProfile>(key: K, value: PolymeraseProfile[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      setError("");
      await onSave(form);
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save polymerase");
    } finally {
      setSaving(false);
    }
  };

  const num = <K extends NumericPolymeraseKey>(key: K) => ({
    value: String(form[key] ?? ""),
    onChange: (e: React.ChangeEvent<HTMLInputElement>) => {
      const next = e.target.value;
      if (isOptionalNumericPolymeraseKey(key)) {
        update(key, parsePolymeraseNumber(key, next));
        return;
      }
      update(key, parsePolymeraseNumber(key, next));
    },
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle className="text-xl">Custom Polymerase</DialogTitle>
          <DialogDescription className="text-muted-foreground">
            Primer design defaults and asymmetric Tm targets for KURO.
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-2 gap-4 text-sm">
          <div className="col-span-2 rounded-2xl border border-border bg-card p-4">
            <label className="text-xs text-muted-foreground">Name</label>
            <Input value={form.name} onChange={(e) => update("name", e.target.value)} />
          </div>
          <div className="rounded-2xl border border-border bg-card p-4">
            <label className="text-xs text-muted-foreground">Tm method</label>
            <select
              className="flex h-9 w-full rounded-xl border border-input bg-white px-3 py-1 text-sm"
              value={form.tm_method}
              onChange={(e) => update("tm_method", e.target.value)}
            >
              <option value="santalucia" title="SantaLucia 1998 nearest-neighbour parameters. Modern default; accurate for most PCR primers (DNA/DNA, 25-mers, physiological salt).">SantaLucia</option>
              <option value="breslauer" title="Breslauer 1986 nearest-neighbour parameters. Legacy table; tends to overestimate Tm vs SantaLucia by 1-3 °C.">Breslauer</option>
            </select>
          </div>
          <div className="rounded-2xl border border-border bg-card p-4">
            <label className="text-xs text-muted-foreground">Salt correction</label>
            <select
              className="flex h-9 w-full rounded-xl border border-input bg-white px-3 py-1 text-sm"
              value={form.salt_correction}
              onChange={(e) => update("salt_correction", e.target.value)}
            >
              <option value="owczarzy" title="Owczarzy 2004/2008 monovalent + Mg²⁺ correction. Recommended when Mg²⁺ or dNTP concentrations are non-standard.">Owczarzy</option>
              <option value="santalucia" title="SantaLucia 1996 monovalent-only correction. Suitable for standard buffers without Mg²⁺ adjustment.">SantaLucia</option>
              <option value="schildkraut" title="Schildkraut-Lifson 1965 empirical Na⁺ correction. Legacy; coarser than Owczarzy or SantaLucia.">Schildkraut</option>
            </select>
          </div>
          <div className="rounded-2xl border border-border bg-card p-4">
            <label className="text-xs text-muted-foreground">Opt Tm</label>
            <Input type="number" step="0.1" {...num("opt_tm")} />
          </div>
          <div className="rounded-2xl border border-border bg-card p-4">
            <label className="text-xs text-muted-foreground">Max Tm diff</label>
            <Input type="number" step="0.1" {...num("max_tm_diff")} />
          </div>
          <div className="rounded-2xl border border-border bg-card p-4">
            <label className="text-xs text-muted-foreground">Min Tm</label>
            <Input type="number" step="0.1" {...num("min_tm")} />
          </div>
          <div className="rounded-2xl border border-border bg-card p-4">
            <label className="text-xs text-muted-foreground">Max Tm</label>
            <Input type="number" step="0.1" {...num("max_tm")} />
          </div>
          <div className="rounded-2xl border border-border bg-card p-4">
            <label className="text-xs text-muted-foreground">Fwd Tm</label>
            <Input type="number" step="0.1" {...num("opt_tm_fwd")} />
          </div>
          <div className="rounded-2xl border border-border bg-card p-4">
            <label className="text-xs text-muted-foreground">Rev Tm</label>
            <Input type="number" step="0.1" {...num("opt_tm_rev")} />
          </div>
          <div className="rounded-2xl border border-border bg-card p-4">
            <label className="text-xs text-muted-foreground">Overlap Tm</label>
            <Input type="number" step="0.1" {...num("opt_tm_overlap")} />
          </div>
          <div className="rounded-2xl border border-border bg-card p-4">
            <label className="text-xs text-muted-foreground">Min 3' distance</label>
            <Input type="number" {...num("min_3prime_dist")} />
          </div>
          <div className="rounded-2xl border border-border bg-card p-4">
            <label className="text-xs text-muted-foreground">Opt size</label>
            <Input type="number" {...num("opt_size")} />
          </div>
          <div className="rounded-2xl border border-border bg-card p-4">
            <label className="text-xs text-muted-foreground">Min size</label>
            <Input type="number" {...num("min_size")} />
          </div>
          <div className="rounded-2xl border border-border bg-card p-4">
            <label className="text-xs text-muted-foreground">Max size</label>
            <Input type="number" {...num("max_size")} />
          </div>
          <div className="rounded-2xl border border-border bg-card p-4">
            <label className="text-xs text-muted-foreground">Min GC</label>
            <Input type="number" step="0.1" {...num("min_gc")} />
          </div>
          <div className="rounded-2xl border border-border bg-card p-4">
            <label className="text-xs text-muted-foreground">Max GC</label>
            <Input type="number" step="0.1" {...num("max_gc")} />
          </div>
          <div className="rounded-2xl border border-border bg-card p-4">
            <label className="text-xs text-muted-foreground">Monovalent salt</label>
            <Input type="number" step="0.1" {...num("salt_monovalent")} />
          </div>
          <div className="rounded-2xl border border-border bg-card p-4">
            <label className="text-xs text-muted-foreground">Divalent salt</label>
            <Input type="number" step="0.1" {...num("salt_divalent")} />
          </div>
          <div className="rounded-2xl border border-border bg-card p-4">
            <label className="text-xs text-muted-foreground">dNTP</label>
            <Input type="number" step="0.1" {...num("dntp_conc")} />
          </div>
          <div className="rounded-2xl border border-border bg-card p-4">
            <label className="text-xs text-muted-foreground">DNA conc</label>
            <Input type="number" step="0.1" {...num("dna_conc")} />
          </div>
        </div>

        {error && <div className="text-sm text-destructive">{error}</div>}

        <DialogFooter>
          <Button variant="outline" className="rounded-full" onClick={() => onOpenChange(false)} disabled={saving}>
            Cancel
          </Button>
          <Button className="rounded-full" onClick={handleSave} disabled={saving || !form.name.trim()}>
            {saving ? "Saving..." : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
