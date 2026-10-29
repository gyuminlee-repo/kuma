import { useEffect, useState, type ChangeEvent, type KeyboardEvent } from "react";

/**
 * A numeric field that keeps a draft while the operator types and commits it
 * on blur or Enter, then shows what the store actually holds.
 *
 * The fields this replaces pushed the store value back into the draft only
 * when the store value changed. A commit the setter normalized to the value
 * it already held (blank to a fallback, 12 to a 10 ceiling, 1.5 to 1) left the
 * store unchanged, so the field kept the rejected text while every consumer
 * read another number. Here the draft is dropped on every commit and the field
 * renders `format(value)` again, so the two cannot disagree after a commit,
 * whatever the setter does.
 *
 * `parse` carries each field's own meaning: it returns the number to commit,
 * or `undefined` when the text states nothing this field accepts, in which
 * case nothing is committed and the stored value comes back. A field whose
 * old rule committed a fallback for unreadable text returns that fallback.
 */
export interface NumberFieldOptions<T> {
  /** The stored value the field shows when no draft is being typed. */
  value: T;
  /** The value a text commits, or `undefined` to commit nothing. */
  parse: (text: string) => T | undefined;
  commit: (next: T) => void;
  /** How the stored value is written into the field. Defaults to `String`. */
  format?: (value: T) => string;
}

export interface NumberField {
  /** What the field shows: the draft while typing, else the stored value. */
  text: string;
  /** Spread onto the `<input type="number">`. */
  inputProps: {
    value: string;
    onChange: (event: ChangeEvent<HTMLInputElement>) => void;
    onBlur: () => void;
    onKeyDown: (event: KeyboardEvent<HTMLInputElement>) => void;
  };
}

export function useNumberField<T>({
  value,
  parse,
  commit,
  format = String,
}: NumberFieldOptions<T>): NumberField {
  const [draft, setDraft] = useState<string | null>(null);
  // A store change from elsewhere (project restore, Clear All) replaces a
  // draft, as every one of these fields did before.
  useEffect(() => setDraft(null), [value]);

  const text = draft ?? format(value);
  const onBlur = () => {
    if (draft === null) return;
    const parsed = parse(draft);
    if (parsed !== undefined) commit(parsed);
    setDraft(null);
  };
  return {
    text,
    inputProps: {
      value: text,
      onChange: (event) => setDraft(event.target.value),
      onBlur,
      onKeyDown: (event) => {
        if (event.key === "Enter") event.currentTarget.blur();
      },
    },
  };
}
