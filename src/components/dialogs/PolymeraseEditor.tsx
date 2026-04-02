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

  const num = (key: keyof PolymeraseProfile) => ({
    value: String((form[key] as number | null | undefined) ?? ""),
    onChange: (e: React.ChangeEvent<HTMLInputElement>) => {
      const next = e.target.value;
      update(key, (next === "" ? null : Number(next)) as PolymeraseProfile[typeof key]);
    },
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Custom Polymerase</DialogTitle>
          <DialogDescription>
            Primer design defaults and asymmetric Tm targets for KURO.
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-2 gap-3 text-sm">
          <div className="col-span-2">
            <label className="text-xs text-gray-500">Name</label>
            <Input value={form.name} onChange={(e) => update("name", e.target.value)} />
          </div>
          <div>
            <label className="text-xs text-gray-500">Tm method</label>
            <select
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm"
              value={form.tm_method}
              onChange={(e) => update("tm_method", e.target.value)}
            >
              <option value="santalucia">SantaLucia</option>
              <option value="breslauer">Breslauer</option>
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-500">Salt correction</label>
            <select
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm"
              value={form.salt_correction}
              onChange={(e) => update("salt_correction", e.target.value)}
            >
              <option value="owczarzy">Owczarzy</option>
              <option value="santalucia">SantaLucia</option>
              <option value="schildkraut">Schildkraut</option>
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-500">Opt Tm</label>
            <Input type="number" step="0.1" {...num("opt_tm")} />
          </div>
          <div>
            <label className="text-xs text-gray-500">Max Tm diff</label>
            <Input type="number" step="0.1" {...num("max_tm_diff")} />
          </div>
          <div>
            <label className="text-xs text-gray-500">Min Tm</label>
            <Input type="number" step="0.1" {...num("min_tm")} />
          </div>
          <div>
            <label className="text-xs text-gray-500">Max Tm</label>
            <Input type="number" step="0.1" {...num("max_tm")} />
          </div>
          <div>
            <label className="text-xs text-gray-500">Fwd Tm</label>
            <Input type="number" step="0.1" {...num("opt_tm_fwd")} />
          </div>
          <div>
            <label className="text-xs text-gray-500">Rev Tm</label>
            <Input type="number" step="0.1" {...num("opt_tm_rev")} />
          </div>
          <div>
            <label className="text-xs text-gray-500">Overlap Tm</label>
            <Input type="number" step="0.1" {...num("opt_tm_overlap")} />
          </div>
          <div>
            <label className="text-xs text-gray-500">Min 3' distance</label>
            <Input type="number" {...num("min_3prime_dist")} />
          </div>
          <div>
            <label className="text-xs text-gray-500">Opt size</label>
            <Input type="number" {...num("opt_size")} />
          </div>
          <div>
            <label className="text-xs text-gray-500">Min size</label>
            <Input type="number" {...num("min_size")} />
          </div>
          <div>
            <label className="text-xs text-gray-500">Max size</label>
            <Input type="number" {...num("max_size")} />
          </div>
          <div>
            <label className="text-xs text-gray-500">Min GC</label>
            <Input type="number" step="0.1" {...num("min_gc")} />
          </div>
          <div>
            <label className="text-xs text-gray-500">Max GC</label>
            <Input type="number" step="0.1" {...num("max_gc")} />
          </div>
          <div>
            <label className="text-xs text-gray-500">Monovalent salt</label>
            <Input type="number" step="0.1" {...num("salt_monovalent")} />
          </div>
          <div>
            <label className="text-xs text-gray-500">Divalent salt</label>
            <Input type="number" step="0.1" {...num("salt_divalent")} />
          </div>
          <div>
            <label className="text-xs text-gray-500">dNTP</label>
            <Input type="number" step="0.1" {...num("dntp_conc")} />
          </div>
          <div>
            <label className="text-xs text-gray-500">DNA conc</label>
            <Input type="number" step="0.1" {...num("dna_conc")} />
          </div>
        </div>

        {error && <div className="text-sm text-red-600">{error}</div>}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={saving || !form.name.trim()}>
            {saving ? "Saving..." : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
