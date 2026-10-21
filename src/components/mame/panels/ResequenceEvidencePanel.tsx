import { useState } from "react";
import { useTranslation } from "react-i18next";
import { resequenceStore, useMameAppStore } from "@/store/mame/mameAppStore";
import type { CloneEvidenceLink, ResequenceEvidence } from "@/types/mame/resequence";
import { Button } from "@/components/ui/button";
import { nbLabel } from "@/lib/mame/nbLabel";
import { allWellsInPlateOrder } from "@/lib/mame/wellSelection";

interface Props {
  readonly value: ResequenceEvidence | null;
  readonly verdictPath: string;
  readonly onChange: (value: ResequenceEvidence | null) => void;
}

export function ResequenceEvidencePanel({ value, verdictPath, onChange }: Props) {
  const { t } = useTranslation();
  const original = useMameAppStore((s) => s.analyzeResult);
  const originalWells = useMameAppStore((s) => s.wells);
  const repeated = resequenceStore((s) => s.analyzeResult);
  const repeatWells = resequenceStore((s) => s.wells);
  const [sourceKey, setSourceKey] = useState("");
  const [repeatKey, setRepeatKey] = useState("");
  const [sameClone, setSameClone] = useState(false);
  const [relationship, setRelationship] = useState<CloneEvidenceLink["relationship"] | "">("");
  const [activityWell, setActivityWell] = useState("");
  const key = (plate: string, well: string) => `${plate}:${well}`;
  const sources = originalWells.filter((well) => well.mutant_id && well.mutant_id !== "WT");
  const candidates = repeatWells.filter((well) =>
    well.selected && well.verdict === "PASS" && !well.is_fallback && !well.manually_confirmed);
  const source = sources.find((well) => key(well.native_barcode, well.well) === sourceKey);
  const repeat = candidates.find((well) => key(well.native_barcode, well.well) === repeatKey);
  const compatible = relationship === "measured_resequence_clone"
    ? Boolean(repeat && activityWell)
    : relationship === "same_clone" && source && repeat && source.mutant_id === repeat.mutant_id;
  const current = original?.output_path === verdictPath && repeated
    && (!value || (value.original_verdict_xlsx === verdictPath && value.verdict_xlsx === repeated.output_path));
  if (!repeated && !value) return null;
  return (
    <section className="space-y-3 rounded-panel border border-border p-3 text-foreground">
      <h3 className="text-sm font-semibold">{t("mame.resequence.evidenceTitle")}</h3>
      <p className="text-sm text-muted-foreground">{t("mame.resequence.evidenceDescription")}</p>
      <p className="break-all text-caption">{value?.verdict_xlsx ?? repeated?.output_path}</p>
      {!current && value && <p role="alert" className="text-sm text-error">{t("mame.resequence.staleMapping")}</p>}
      <select aria-label={t("mame.resequence.relationship")} className="w-full min-w-0 rounded-control border bg-background p-2 text-sm"
        value={relationship} onChange={(event) => {
          const selected = event.target.value;
          if (selected === "" || selected === "same_clone" || selected === "measured_resequence_clone") setRelationship(selected);
          setSameClone(false);
        }}>
        <option value="">{t("mame.resequence.relationship")}</option>
        <option value="same_clone">{t("mame.resequence.originalClone")}</option>
        <option value="measured_resequence_clone">{t("mame.resequence.measuredClone")}</option>
      </select>
      <div className="flex flex-wrap gap-2">
        {relationship === "same_clone" && <select aria-label={t("mame.resequence.originalClone")} className="min-w-0 flex-1 rounded-control border bg-background p-2 text-sm"
          value={sourceKey} onChange={(event) => { setSourceKey(event.target.value); setSameClone(false); }}>
          <option value="">{t("mame.resequence.originalClone")}</option>
          {sources.map((well) => <option key={key(well.native_barcode, well.well)} value={key(well.native_barcode, well.well)}>
            {well.mutant_id} / {nbLabel(well.native_barcode)} / {well.well}
          </option>)}
        </select>}
        {relationship === "measured_resequence_clone" && <select aria-label={t("mame.resequence.activityWell")} className="min-w-0 flex-1 rounded-control border bg-background p-2 text-sm"
          value={activityWell} onChange={(event) => { setActivityWell(event.target.value); setSameClone(false); }}>
          <option value="">{t("mame.resequence.activityWell")}</option>
          {allWellsInPlateOrder().map((well) => <option key={well} value={well}>{well}</option>)}
        </select>}
        <select aria-label={t("mame.resequence.repeatedClone")} className="min-w-0 flex-1 rounded-control border bg-background p-2 text-sm"
          value={repeatKey} onChange={(event) => { setRepeatKey(event.target.value); setSameClone(false); }}>
          <option value="">{t("mame.resequence.repeatedClone")}</option>
          {candidates.map((well) => <option key={key(well.native_barcode, well.well)} value={key(well.native_barcode, well.well)}>
            {well.mutant_id} / {nbLabel(well.native_barcode)} / {well.well}
          </option>)}
        </select>
      </div>
      <label className="flex items-start gap-2 text-sm">
        <input type="checkbox" checked={sameClone} onChange={(event) => setSameClone(event.target.checked)} />
        {t(relationship === "measured_resequence_clone" ? "mame.resequence.measuredConfirm" : "mame.resequence.sameClone")}
      </label>
      {relationship === "same_clone" && source && repeat && !compatible && <p role="alert" className="text-sm text-error">{t("mame.resequence.incompatible")}</p>}
      <Button type="button" size="sm" disabled={!current || !compatible || !sameClone} onClick={() => {
        if (!original || !repeated || !repeat || !relationship || !compatible || !sameClone) return;
        onChange({
          original_verdict_xlsx: original.output_path,
          verdict_xlsx: repeated.output_path,
          links: [...(value?.links ?? []).filter((link) => link.mutant_id !== repeat.mutant_id), {
            relationship,
            mutant_id: repeat.mutant_id,
            original_well: relationship === "same_clone" ? source?.well ?? "" : "",
            original_plate: relationship === "same_clone" ? source?.native_barcode ?? "" : "",
            ...(relationship === "measured_resequence_clone" ? { activity_well: activityWell } : {}),
            resequence_well: repeat.well,
            resequence_plate: repeat.native_barcode,
          }],
        });
        setSameClone(false);
      }}>{t("mame.resequence.linkEvidence")}</Button>
      {value?.links.map((link) => <div className="flex flex-wrap items-center gap-2 text-sm" key={link.mutant_id}>
        <span className="min-w-0 flex-1">{link.mutant_id}: {link.relationship === "measured_resequence_clone"
          ? `${t("mame.resequence.activityWell")} ${link.activity_well}`
          : `${nbLabel(link.original_plate)} / ${link.original_well}`} → {nbLabel(link.resequence_plate)} / {link.resequence_well}</span>
        <Button variant="ghost" size="sm" onClick={() => {
          const links = value.links.filter((item) => item !== link);
          onChange(links.length ? { ...value, links } : null);
        }}>{t("mame.resequence.removeLink")}</Button>
      </div>)}
    </section>
  );
}
