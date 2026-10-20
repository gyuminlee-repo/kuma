import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertCircle, Undo2, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { nbLabel, nbOrderKey } from "@/lib/mame/nbLabel";
import {
  MAX_OVERRIDE_NOTE_LENGTH,
  needsConfirmation,
  selectedVerdict,
  wellOfMutant,
} from "@/lib/mame/selectionOverrides";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import type { ReplicateResult } from "@/types/mame/models";
import { VerdictBadge } from "./VerdictBadge";

interface EditorProps {
  replicate: ReplicateResult;
  busy: boolean;
  onConfirm: (plate: string, note: string) => void;
  onCancel: () => void;
}

function CopyEditor({ replicate, busy, onConfirm, onCancel }: EditorProps) {
  const { t } = useTranslation();
  const copies = useMemo(
    () =>
      Object.keys(replicate.plate_verdicts).sort(
        (a, b) => nbOrderKey(a) - nbOrderKey(b),
      ),
    [replicate.plate_verdicts],
  );
  const [plate, setPlate] = useState<string>(
    replicate.manual ? (replicate.selected_plate ?? "") : "",
  );
  const [note, setNote] = useState<string>(replicate.manual?.note ?? "");
  const noteId = `manual-note-${replicate.mutant_id}`;

  return (
    <div className="min-w-0 space-y-2 rounded-control border border-border bg-muted/30 p-2.5">
      <fieldset className="min-w-0 space-y-1">
        <legend className="text-caption font-medium text-foreground">
          {t("mame.manualConfirm.copiesLegend", { mutant: replicate.mutant_id })}
        </legend>
        {copies.map((copy) => {
          const verdict = replicate.plate_verdicts[copy].verdict;
          return (
            <label
              key={copy}
              className="flex min-w-0 cursor-pointer items-center gap-2 text-caption"
            >
              <input
                type="radio"
                name={`manual-copy-${replicate.mutant_id}`}
                value={copy}
                checked={plate === copy}
                onChange={() => setPlate(copy)}
              />
              <span className="font-medium">{nbLabel(copy)}</span>
              <VerdictBadge verdict={verdict} />
            </label>
          );
        })}
      </fieldset>
      <div className="space-y-1">
        <label htmlFor={noteId} className="text-caption font-medium text-foreground">
          {t("mame.manualConfirm.noteLabel")}
        </label>
        <Input
          id={noteId}
          value={note}
          maxLength={MAX_OVERRIDE_NOTE_LENGTH}
          placeholder={t("mame.manualConfirm.notePlaceholder")}
          onChange={(e) => setNote(e.target.value)}
          className="h-control min-w-0 text-caption"
        />
      </div>
      <div className="flex gap-2">
        <Button
          size="sm"
          className="h-control rounded-control text-caption"
          disabled={busy || plate === ""}
          onClick={() => onConfirm(plate, note)}
        >
          {t("mame.manualConfirm.confirm")}
        </Button>
        <Button
          size="sm"
          variant="outline"
          className="h-control rounded-control text-caption"
          onClick={onCancel}
        >
          {t("mame.manualConfirm.cancel")}
        </Button>
      </div>
    </div>
  );
}

export function AdditionalSequencingPanel() {
  const { t } = useTranslation();
  const replicates = useMameAppStore((s) => s.replicates);
  const wells = useMameAppStore((s) => s.wells);
  const notice = useMameAppStore((s) => s.selectionOverrideNotice);
  const error = useMameAppStore((s) => s.selectionOverrideError);
  const workbookError = useMameAppStore((s) => s.selectionOverrideWorkbookError);
  const busy = useMameAppStore((s) => s.isApplyingSelectionOverride);
  const apply = useMameAppStore((s) => s.applySelectionOverride);
  const undo = useMameAppStore((s) => s.undoSelectionOverride);
  const dismiss = useMameAppStore((s) => s.dismissSelectionOverrideNotice);
  const [editing, setEditing] = useState<string | null>(null);

  const needing = useMemo(() => replicates.filter(needsConfirmation), [replicates]);
  const confirmed = useMemo(() => replicates.filter((r) => r.manual), [replicates]);
  const editingReplicate = replicates.find((r) => r.mutant_id === editing) ?? null;

  if (replicates.length === 0) return null;

  const label = (rr: ReplicateResult) => {
    const well = wellOfMutant(wells, rr.mutant_id);
    return well ? `${rr.mutant_id} (${well})` : rr.mutant_id;
  };

  return (
    <section
      aria-labelledby="manual-confirm-title"
      className="mt-3 min-w-0 space-y-3 rounded-control border border-border p-3"
    >
      <div className="space-y-0.5">
        <h3 id="manual-confirm-title" className="text-body font-semibold">
          {t("mame.manualConfirm.title")}
        </h3>
        <p className="text-caption text-muted-foreground">
          {t("mame.manualConfirm.description")}
        </p>
      </div>

      {notice && (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-control border border-warning/40 bg-warning/10 px-2.5 py-1.5"
        >
          <AlertCircle size={12} className="mt-0.5 flex-shrink-0 text-warning" aria-hidden="true" />
          <div className="min-w-0 flex-1 space-y-1 text-caption">
            <p className="font-medium">{t("mame.manualConfirm.droppedTitle")}</p>
            <ul className="list-disc pl-4">
              {notice.map((d) => (
                <li key={`${d.mutant_id}|${d.plate}`} className="break-words">
                  {t("mame.manualConfirm.droppedItem", {
                    mutant: d.mutant_id,
                    copy: nbLabel(d.plate),
                    reason: t(`mame.manualConfirm.dropReason.${d.reason}`),
                  })}
                </li>
              ))}
            </ul>
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="h-6 w-6 p-0"
            aria-label={t("mame.manualConfirm.dismiss")}
            onClick={dismiss}
          >
            <X size={12} aria-hidden="true" />
          </Button>
        </div>
      )}

      {error && (
        <p role="alert" className="break-words text-caption text-error">
          {t("mame.manualConfirm.error", { message: error })}
        </p>
      )}

      {workbookError !== null && (
        <p role="alert" className="break-words text-caption text-warning">
          {t("mame.manualConfirm.workbookFailed", { message: workbookError })}
        </p>
      )}

      <div className="space-y-1">
        <h4 className="text-caption font-medium">
          {t("mame.manualConfirm.needsTitle", { count: needing.length })}
        </h4>
        {needing.length === 0 ? (
          <p className="text-caption text-muted-foreground">
            {t("mame.manualConfirm.needsEmpty")}
          </p>
        ) : (
          <ul className="space-y-1">
            {needing.map((rr) => {
              const verdict = selectedVerdict(rr);
              return (
                <li
                  key={rr.mutant_id}
                  className="flex min-w-0 items-center gap-2 text-caption"
                >
                  <span className="min-w-0 flex-1 truncate font-medium" title={label(rr)}>
                    {label(rr)}
                  </span>
                  {rr.selected_plate && verdict ? (
                    <>
                      <span>{nbLabel(rr.selected_plate)}</span>
                      <VerdictBadge verdict={verdict} />
                    </>
                  ) : (
                    <span className="text-muted-foreground">
                      {t("mame.manualConfirm.noCopy")}
                    </span>
                  )}
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-control rounded-control text-caption"
                    onClick={() => setEditing(rr.mutant_id)}
                  >
                    {t("mame.manualConfirm.choose")}
                  </Button>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <div className="flex min-w-0 items-center gap-2">
        <label htmlFor="manual-open-any" className="text-caption font-medium">
          {t("mame.manualConfirm.openAny")}
        </label>
        <select
          id="manual-open-any"
          className="h-control min-w-0 flex-1 rounded-control border border-border bg-background px-2 text-caption"
          value={editing ?? ""}
          onChange={(e) => setEditing(e.target.value === "" ? null : e.target.value)}
        >
          <option value="">{t("mame.manualConfirm.openAnyPlaceholder")}</option>
          {replicates.map((rr) => (
            <option key={rr.mutant_id} value={rr.mutant_id}>
              {label(rr)}
            </option>
          ))}
        </select>
      </div>

      {editingReplicate && (
        <CopyEditor
          key={editingReplicate.mutant_id}
          replicate={editingReplicate}
          busy={busy}
          onCancel={() => setEditing(null)}
          onConfirm={(plate, note) => {
            void apply(editingReplicate.mutant_id, plate, note).then(() =>
              setEditing(null),
            );
          }}
        />
      )}

      {confirmed.length > 0 && (
        <div className="space-y-1">
          <h4 className="text-caption font-medium">
            {t("mame.manualConfirm.confirmedTitle", { count: confirmed.length })}
          </h4>
          <ul className="space-y-1.5">
            {confirmed.map((rr) => {
              const manual = rr.manual;
              if (!manual) return null;
              return (
                <li
                  key={rr.mutant_id}
                  className="flex min-w-0 items-start gap-2 text-caption"
                >
                  <div className="min-w-0 flex-1 space-y-0.5">
                    <div className="flex min-w-0 flex-wrap items-center gap-1.5">
                      <span className="font-medium">{label(rr)}</span>
                      <Badge
                        variant="outline"
                        className="border-primary/40 px-1 py-0 text-primary"
                      >
                        {t("mame.manualConfirm.badge")}
                      </Badge>
                      <span>{rr.selected_plate ? nbLabel(rr.selected_plate) : ""}</span>
                    </div>
                    {manual.note && (
                      <p className="break-words text-muted-foreground">{manual.note}</p>
                    )}
                    <p className="text-muted-foreground">
                      {manual.auto_selected_plate && manual.auto_verdict
                        ? t("mame.manualConfirm.original", {
                            verdict: manual.auto_verdict,
                            copy: nbLabel(manual.auto_selected_plate),
                          })
                        : t("mame.manualConfirm.originalNone")}
                    </p>
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-control gap-1 rounded-control text-caption"
                    disabled={busy}
                    onClick={() => void undo(rr.mutant_id)}
                  >
                    <Undo2 size={12} aria-hidden="true" />
                    {t("mame.manualConfirm.undo")}
                  </Button>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </section>
  );
}
