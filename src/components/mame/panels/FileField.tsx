/**
 * FileField — shared file/folder picker row used across MAME input panels.
 *
 * Layout: label (+ one optional `?`) + status badge (Ready/Optional),
 * a full-path text input with a Browse button, an optional helper line, and a
 * truncated basename preview (full path on hover). Single source of truth so
 * every MAME picker (MinKNOW run folder, barcode seeds, CDS FASTA, output dir,
 * export destination) renders identically.
 */

import type { ReactNode } from "react";
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
  help,
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
  /** One-string help, shown only when no richer `help` control is given. */
  helpText?: string;
  /**
   * Help that is more than one string, such as a table of the file shape. It
   * replaces `helpText` rather than joining it: two "?" buttons side by side
   * give the reader no way to tell which one answers their question, so a
   * field with both folds the sentence into the richer control.
   */
  help?: ReactNode;
  noPathLabel: string;
  readyLabel: string;
  browseAriaLabel?: string;
}) {
  const inputId = `file-field-${label.replace(/\s+/g, "-").toLowerCase()}`;
  const preview = getPathPreview(value);
  const displayValue = value ? preview : "";

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-3">
        {/* The help control is a sibling of the label, never inside it: a
            button inside a <label> is not allowed there, and clicking it would
            also focus the input. */}
        <span className="inline-flex items-center gap-1.5">
          <Label htmlFor={inputId} className="text-caption font-medium uppercase tracking-wide text-muted-foreground">
            {label}
          </Label>
          {help ?? (helpText && <InlineHelp text={helpText} />)}
        </span>
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
          value={displayValue}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="h-8 flex-1 min-w-0 text-xs font-mono"
          aria-label={label}
          title={value || undefined}
          readOnly
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
