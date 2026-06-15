import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import type { CustomEnzyme } from "../../types/models";
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

const DEFAULT_ENZYME: CustomEnzyme = {
  name: "",
  recognition: "",
  cut_offset: [1, 5],
  overhang_len: 4,
  prefix: "",
  aliases: [],
};

interface EnzymeEditorProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSave: (enzyme: CustomEnzyme) => Promise<void>;
}

export function EnzymeEditor({ open, onOpenChange, onSave }: EnzymeEditorProps) {
  const { t } = useTranslation();
  const [form, setForm] = useState<CustomEnzyme>(DEFAULT_ENZYME);
  const [aliasText, setAliasText] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (open) {
      setForm(DEFAULT_ENZYME);
      setAliasText("");
      setError("");
    }
  }, [open]);

  const update = <K extends keyof CustomEnzyme>(key: K, value: CustomEnzyme[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const recognitionInvalid =
    form.recognition.trim() !== "" && /[^acgtACGT]/.test(form.recognition.trim());
  const canSave =
    form.name.trim() !== "" &&
    form.recognition.trim() !== "" &&
    !recognitionInvalid &&
    form.prefix.trim() !== "" &&
    form.overhang_len >= 1;

  const handleSave = async () => {
    try {
      setSaving(true);
      setError("");
      const aliases = aliasText
        .split(/[\s,]+/)
        .map((s) => s.trim())
        .filter(Boolean);
      await onSave({
        ...form,
        name: form.name.trim(),
        recognition: form.recognition.trim().toUpperCase(),
        prefix: form.prefix.trim().toUpperCase(),
        aliases,
      });
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("enzymeEditor.saveError"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle className="text-xl">{t("enzymeEditor.title")}</DialogTitle>
          <DialogDescription className="text-muted-foreground">
            {t("enzymeEditor.description")}
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-2 gap-4 text-sm">
          <div className="col-span-2 rounded-2xl border border-border bg-card p-4">
            <label className="text-xs text-muted-foreground">{t("enzymeEditor.nameLabel")}</label>
            <Input value={form.name} onChange={(e) => update("name", e.target.value)} />
          </div>
          <div className="col-span-2 rounded-2xl border border-border bg-card p-4">
            <label className="text-xs text-muted-foreground">{t("enzymeEditor.recognitionLabel")}</label>
            <Input
              value={form.recognition}
              onChange={(e) => update("recognition", e.target.value)}
              placeholder="GGTCTC"
            />
            {recognitionInvalid && (
              <div className="mt-1 text-xs text-destructive">{t("enzymeEditor.recognitionInvalid")}</div>
            )}
          </div>
          <div className="rounded-2xl border border-border bg-card p-4">
            <label className="text-xs text-muted-foreground">{t("enzymeEditor.cutTopLabel")}</label>
            <Input
              type="number"
              value={String(form.cut_offset[0])}
              onChange={(e) => update("cut_offset", [Number(e.target.value), form.cut_offset[1]])}
            />
          </div>
          <div className="rounded-2xl border border-border bg-card p-4">
            <label className="text-xs text-muted-foreground">{t("enzymeEditor.cutBottomLabel")}</label>
            <Input
              type="number"
              value={String(form.cut_offset[1])}
              onChange={(e) => update("cut_offset", [form.cut_offset[0], Number(e.target.value)])}
            />
          </div>
          <div className="rounded-2xl border border-border bg-card p-4">
            <label className="text-xs text-muted-foreground">{t("enzymeEditor.overhangLenLabel")}</label>
            <Input
              type="number"
              value={String(form.overhang_len)}
              onChange={(e) => update("overhang_len", Number(e.target.value))}
            />
          </div>
          <div className="rounded-2xl border border-border bg-card p-4">
            <label className="text-xs text-muted-foreground">{t("enzymeEditor.aliasesLabel")}</label>
            <Input value={aliasText} onChange={(e) => setAliasText(e.target.value)} placeholder="Eco31I" />
          </div>
          <div className="col-span-2 rounded-2xl border border-border bg-card p-4">
            <label className="text-xs text-muted-foreground">{t("enzymeEditor.prefixLabel")}</label>
            <Input
              value={form.prefix}
              onChange={(e) => update("prefix", e.target.value)}
              placeholder="CTAGGGTCTCA"
            />
            <div className="mt-1 text-xs text-muted-foreground">{t("enzymeEditor.prefixHelp")}</div>
          </div>
        </div>

        {error && <div className="text-sm text-destructive">{error}</div>}

        <DialogFooter>
          <Button variant="outline" className="rounded-full" onClick={() => onOpenChange(false)} disabled={saving}>
            {t("enzymeEditor.cancel")}
          </Button>
          <Button className="rounded-full" onClick={handleSave} disabled={saving || !canSave}>
            {saving ? t("enzymeEditor.saving") : t("enzymeEditor.save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
