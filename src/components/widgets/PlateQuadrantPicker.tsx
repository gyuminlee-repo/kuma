/**
 * PlateQuadrantPicker, visual 2x2 picker for the Echo source-plate quadrant
 * a 96-head Zephyr stamps from.
 *
 * [source: kuma_core/kuro/plate_quadrant.py, read-only reference, not edited here]
 *
 * Replaces a `<select>` with the same four options (A1/A2/B1/B2) plus "not
 * specified". A dropdown hides the one fact that matters here: forward and
 * reverse stay on the same column (A1<->B1, A2<->B2), so picking A1 always
 * puts reverse in B1. Laying the four options out as a 2x2 grid, in the same
 * geometry the physical plate has (row A on top, row B below; column 1 on
 * the left, column 2 on the right), lets that pairing be seen instead of
 * memorized from a caption. `usedQuadrants` renders wherever it did before
 * (independent checkboxes) because the plate is a physical object this
 * program never sees and a stale guess would be worse than a checkbox list.
 */
import { useCallback, useId, useRef } from "react";
import type { KeyboardEvent } from "react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import type { EchoQuadrant } from "@/types/models";

const GRID: EchoQuadrant[] = ["A1", "A2", "B1", "B2"];

/** Quadrant sharing a column with `q` (the paired forward/reverse quadrant).
 *  Mirrors kuma_core/kuro/plate_quadrant.py `paired_quadrant`: A1<->B1 and
 *  A2<->B2 (same column offset, opposite row offset). */
function pairedQuadrant(q: EchoQuadrant): EchoQuadrant {
  const pairs: Record<EchoQuadrant, EchoQuadrant> = {
    A1: "B1",
    B1: "A1",
    A2: "B2",
    B2: "A2",
  };
  return pairs[q];
}

type Option = EchoQuadrant | "none";

interface Props {
  value: EchoQuadrant | null;
  onChange: (value: EchoQuadrant | null) => void;
  usedQuadrants: EchoQuadrant[];
  onUsedQuadrantsChange: (value: EchoQuadrant[]) => void;
}

export function PlateQuadrantPicker({
  value,
  onChange,
  usedQuadrants,
  onUsedQuadrantsChange,
}: Props) {
  const { t } = useTranslation();
  const groupId = useId();
  const refs = useRef<Partial<Record<Option, HTMLButtonElement | null>>>({});

  const current: Option = value ?? "none";

  const focusOption = useCallback((opt: Option) => {
    refs.current[opt]?.focus();
  }, []);

  /** Arrow-key neighbour lookup over the 2x2 grid plus the "none" row below
   *  it. Down from either bottom cell reaches "none"; up from "none" returns
   *  to B1 (no column memory needed for four cells). */
  const neighbour = useCallback((from: Option, key: string): Option | null => {
    switch (key) {
      case "ArrowRight":
        if (from === "A1") return "A2";
        if (from === "B1") return "B2";
        return null;
      case "ArrowLeft":
        if (from === "A2") return "A1";
        if (from === "B2") return "B1";
        return null;
      case "ArrowDown":
        if (from === "A1") return "B1";
        if (from === "A2") return "B2";
        if (from === "B1" || from === "B2") return "none";
        return null;
      case "ArrowUp":
        if (from === "B1") return "A1";
        if (from === "B2") return "A2";
        if (from === "none") return "B1";
        return null;
      default:
        return null;
    }
  }, []);

  const select = useCallback(
    (opt: Option) => {
      onChange(opt === "none" ? null : opt);
    },
    [onChange],
  );

  const onKeyDown = useCallback(
    (event: KeyboardEvent<HTMLButtonElement>, opt: Option) => {
      if (
        event.key === "ArrowRight" ||
        event.key === "ArrowLeft" ||
        event.key === "ArrowDown" ||
        event.key === "ArrowUp"
      ) {
        const next = neighbour(opt, event.key);
        if (next) {
          event.preventDefault();
          focusOption(next);
        }
        return;
      }
      if (event.key === " " || event.key === "Enter") {
        event.preventDefault();
        select(opt);
      }
    },
    [neighbour, focusOption, select],
  );

  const renderCell = (opt: Option, label: string, extraClassName?: string) => {
    const selected = current === opt;
    const isPaired =
      value !== null && opt !== "none" && opt !== value && pairedQuadrant(value) === opt;
    return (
      <button
        key={opt}
        ref={(el) => {
          refs.current[opt] = el;
        }}
        type="button"
        role="radio"
        aria-checked={selected}
        tabIndex={selected ? 0 : -1}
        onClick={() => select(opt)}
        onKeyDown={(event) => onKeyDown(event, opt)}
        className={cn(
          "flex h-11 items-center justify-center rounded-md border text-sm font-medium transition-colors",
          selected
            ? "border-primary bg-primary/10 text-foreground"
            : isPaired
              ? "border-primary/40 bg-primary/5 text-muted-foreground"
              : "border-border text-muted-foreground hover:bg-muted",
          extraClassName,
        )}
      >
        {label}
      </button>
    );
  };

  return (
    <div className="flex flex-col gap-1">
      <span id={`${groupId}-label`} className="text-sm font-medium text-foreground">
        {t("phaseC.export.all.quadrantLabel")}
      </span>
      <div
        role="radiogroup"
        aria-labelledby={`${groupId}-label`}
        className="flex flex-col gap-2 w-fit"
      >
        <div className="grid grid-cols-2 gap-1 w-40">
          {renderCell("A1", "A1")}
          {renderCell("A2", "A2")}
          {renderCell("B1", "B1")}
          {renderCell("B2", "B2")}
        </div>
        {renderCell("none", t("phaseC.export.all.quadrantNone"), "w-40 h-9 text-caption")}
      </div>
      <p className="text-caption text-muted-foreground">
        {t("phaseC.export.all.quadrantHelper")}
      </p>

      {/* 이미 소진된 quadrant. plate 는 kuma 가 볼 수 없는 물건이라 작업자가 말한다. */}
      {value !== null && (
        <div className="flex flex-col gap-1 mt-2">
          <span className="text-sm font-medium text-foreground">
            {t("phaseC.export.all.usedQuadrantsLabel")}
          </span>
          <div className="flex flex-wrap gap-3">
            {GRID.map((q) => (
              <label key={q} className="flex items-center gap-1.5 text-sm">
                <input
                  type="checkbox"
                  checked={usedQuadrants.includes(q)}
                  onChange={(e) =>
                    onUsedQuadrantsChange(
                      e.target.checked
                        ? [...usedQuadrants, q]
                        : usedQuadrants.filter((x) => x !== q),
                    )
                  }
                />
                {q}
              </label>
            ))}
          </div>
          <p className="text-caption text-muted-foreground">
            {t("phaseC.export.all.usedQuadrantsHelper")}
          </p>
        </div>
      )}
    </div>
  );
}
