/**
 * FileField — shared file/folder picker row used across MAME input panels.
 *
 * Layout: label (+ optional `?` InlineHelp) + status badge (Ready/Optional),
 * a full-path text input with a Browse button, an optional helper line, and a
 * truncated basename preview (full path on hover). Single source of truth so
 * every MAME picker (MinKNOW run folder, barcode seeds, CDS FASTA, output dir,
 * export destination) renders identically.
 */

import { FolderOpen } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { InlineHelp } from "@/components/ui/InlineHelp";

/** Last path segment (basename) for the truncated preview line. */
export function getPathPreview(value: string): string {
  if (!value) return "";
  const parts = value.split(/[/\\]/);
  return parts[parts.length - 1] || value;
}

export function FileField({
  label,
  value,
  onChange,
  onBrowse,
  placeholder,
  stateLabel,
  filled,
  helperText,
  helpText,
  noPathLabel,
  readyLabel,
  browseAriaLabel,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  onBrowse: () => Promise<void>;
  placeholder?: string;
  stateLabel: string;
  filled: boolean;
  helperText?: string;
  helpText?: string;
  noPathLabel: string;
  readyLabel: string;
  browseAriaLabel?: string;
}) {
  const inputId = `file-field-${label.replace(/\s+/g, "-").toLowerCase()}`;
  const preview = getPathPreview(value);

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-3">
        <Label htmlFor={inputId} className="text-caption font-medium uppercase tracking-wide text-muted-foreground">
          <span className="inline-flex items-center gap-1.5">
            {label}
            {helpText && <InlineHelp text={helpText} />}
          </span>
        </Label>
        <span
          className={`rounded-full px-2 py-0.5 text-caption font-medium ${
            filled
              ? "bg-primary/10 text-primary"
              : "bg-muted text-muted-foreground"
          }`}
        >
          {filled ? readyLabel : stateLabel}
        </span>
      </div>
      <div className="flex gap-1.5">
        <Input
          id={inputId}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="h-8 flex-1 min-w-0 text-xs font-mono"
          aria-label={label}
        />
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => void onBrowse()}
          className="h-8 gap-1 px-2"
          aria-label={browseAriaLabel ?? label}
        >
          <FolderOpen size={12} aria-hidden="true" />
        </Button>
      </div>
      {helperText && (
        <p className="text-caption text-muted-foreground/90">{helperText}</p>
      )}
      <p className="truncate text-caption text-muted-foreground" title={value || undefined}>
        {filled ? preview : noPathLabel}
      </p>
    </div>
  );
}
