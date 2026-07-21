import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

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

const NEB_TM_PROFILES = ["Q5", "Q5 SDM", "Phusion", "Taq"];

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
  const { t } = useTranslation();
  const [form, setForm] = useState<PolymeraseProfile>(profile ?? DEFAULT_PROFILE);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const isNebTmProfile = NEB_TM_PROFILES.includes(form.name);

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
      setError(err instanceof Error ? err.message : t("polymeraseEditor.saveError"));
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
          <DialogTitle className="text-xl">{t("polymeraseEditor.title")}</DialogTitle>
          <DialogDescription className="text-muted-foreground">
            {t("polymeraseEditor.description")}
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-2 gap-4 text-sm">
          <div className="col-span-2 rounded-2xl border border-border bg-card p-4">
            <label className="text-xs text-muted-foreground">{t("polymeraseEditor.nameLabel")}</label>
            <Input value={form.name} onChange={(e) => update("name", e.target.value)} />
          </div>
          <div className="rounded-2xl border border-border bg-card p-4">
            <label className="text-xs text-muted-foreground">{t("polymeraseEditor.tmMethodLabel")}</label>
            <select
              className="flex h-9 w-full rounded-xl border border-input bg-white px-3 py-1 text-sm"
              value={form.tm_method}
              onChange={(e) => update("tm_method", e.target.value)}
            >
              <option value="santalucia" title={t("polymeraseEditor.tmMethodOption_santalucia_title")}>{t("polymeraseEditor.tmMethodOption_santalucia")}</option>
              <option value="breslauer" title={t("polymeraseEditor.tmMethodOption_breslauer_title")}>{t("polymeraseEditor.tmMethodOption_breslauer")}</option>
            </select>
          </div>
          <div className="rounded-2xl border border-border bg-card p-4">
            <label className="text-xs text-muted-foreground">{t("polymeraseEditor.saltCorrectionLabel")}</label>
            <select
              className="flex h-9 w-full rounded-xl border border-input bg-white px-3 py-1 text-sm"
              value={form.salt_correction}
              onChange={(e) => update("salt_correction", e.target.value)}
            >
              <option value="owczarzy" title={t("polymeraseEditor.saltOption_owczarzy_title")}>{t("polymeraseEditor.saltOption_owczarzy")}</option>
              <option value="santalucia" title={t("polymeraseEditor.saltOption_santalucia_title")}>{t("polymeraseEditor.saltOption_santalucia")}</option>
              <option value="schildkraut" title={t("polymeraseEditor.saltOption_schildkraut_title")}>{t("polymeraseEditor.saltOption_schildkraut")}</option>
            </select>
          </div>
          {isNebTmProfile && (
            <div className="col-span-2 rounded-2xl border border-border bg-muted/40 p-3 text-xs text-muted-foreground">
              {t("polymeraseEditor.nebTmNote")}
            </div>
          )}
          <div className="col-span-2 rounded-2xl border border-border bg-muted/40 p-3 text-xs text-muted-foreground">
            {t("polymeraseEditor.fieldScopeNote")}
          </div>
          <div className="rounded-2xl border border-border bg-card p-4">
            <label className="text-xs text-muted-foreground">{t("polymeraseEditor.optTmLabel")}</label>
            <Input type="number" step="0.1" {...num("opt_tm")} />
          </div>
          <div className="rounded-2xl border border-border bg-card p-4">
            <label className="text-xs text-muted-foreground">{t("polymeraseEditor.maxTmDiffLabel")}</label>
            <Input type="number" step="0.1" {...num("max_tm_diff")} />
          </div>
          <div className="rounded-2xl border border-border bg-card p-4">
            <label className="text-xs text-muted-foreground">{t("polymeraseEditor.minTmLabel")}</label>
            <Input type="number" step="0.1" {...num("min_tm")} />
          </div>
          <div className="rounded-2xl border border-border bg-card p-4">
            <label className="text-xs text-muted-foreground">{t("polymeraseEditor.maxTmLabel")}</label>
            <Input type="number" step="0.1" {...num("max_tm")} />
          </div>
          <div className="rounded-2xl border border-border bg-card p-4">
            <label className="text-xs text-muted-foreground">{t("polymeraseEditor.fwdTmLabel")}</label>
            <Input type="number" step="0.1" {...num("opt_tm_fwd")} />
          </div>
          <div className="rounded-2xl border border-border bg-card p-4">
            <label className="text-xs text-muted-foreground">{t("polymeraseEditor.revTmLabel")}</label>
            <Input type="number" step="0.1" {...num("opt_tm_rev")} />
          </div>
          <div className="rounded-2xl border border-border bg-card p-4">
            <label className="text-xs text-muted-foreground">{t("polymeraseEditor.overlapTmLabel")}</label>
            <Input type="number" step="0.1" {...num("opt_tm_overlap")} />
          </div>
          <div className="rounded-2xl border border-border bg-card p-4">
            <label className="text-xs text-muted-foreground">{t("polymeraseEditor.min3PrimeDistLabel")}</label>
            <Input type="number" {...num("min_3prime_dist")} />
          </div>
          <div className="rounded-2xl border border-border bg-card p-4">
            <label className="text-xs text-muted-foreground">{t("polymeraseEditor.optSizeLabel")}</label>
            <Input type="number" {...num("opt_size")} />
          </div>
          <div className="rounded-2xl border border-border bg-card p-4">
            <label className="text-xs text-muted-foreground">{t("polymeraseEditor.minSizeLabel")}</label>
            <Input type="number" {...num("min_size")} />
          </div>
          <div className="rounded-2xl border border-border bg-card p-4">
            <label className="text-xs text-muted-foreground">{t("polymeraseEditor.maxSizeLabel")}</label>
            <Input type="number" {...num("max_size")} />
          </div>
          <div className="rounded-2xl border border-border bg-card p-4">
            <label className="text-xs text-muted-foreground">{t("polymeraseEditor.minGcLabel")}</label>
            <Input type="number" step="0.1" {...num("min_gc")} />
          </div>
          <div className="rounded-2xl border border-border bg-card p-4">
            <label className="text-xs text-muted-foreground">{t("polymeraseEditor.maxGcLabel")}</label>
            <Input type="number" step="0.1" {...num("max_gc")} />
          </div>
          <div className="rounded-2xl border border-border bg-card p-4">
            <label className="text-xs text-muted-foreground">{t("polymeraseEditor.monovalentSaltLabel")}</label>
            <Input type="number" step="0.1" {...num("salt_monovalent")} />
          </div>
          <div className="rounded-2xl border border-border bg-card p-4">
            <label className="text-xs text-muted-foreground">{t("polymeraseEditor.divalentSaltLabel")}</label>
            <Input type="number" step="0.1" {...num("salt_divalent")} />
          </div>
          <div className="rounded-2xl border border-border bg-card p-4">
            <label className="text-xs text-muted-foreground">{t("polymeraseEditor.dntpLabel")}</label>
            <Input type="number" step="0.1" {...num("dntp_conc")} />
          </div>
          <div className="rounded-2xl border border-border bg-card p-4">
            <label className="text-xs text-muted-foreground">{t("polymeraseEditor.dnaConcLabel")}</label>
            <Input type="number" step="0.1" {...num("dna_conc")} />
          </div>
        </div>

        {error && <div className="text-sm text-destructive">{error}</div>}

        <DialogFooter>
          <Button variant="outline" className="rounded-full" onClick={() => onOpenChange(false)} disabled={saving}>
            {t("polymeraseEditor.cancel")}
          </Button>
          <Button className="rounded-full" onClick={handleSave} disabled={saving || !form.name.trim()}>
            {saving ? t("polymeraseEditor.saving") : t("polymeraseEditor.save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
