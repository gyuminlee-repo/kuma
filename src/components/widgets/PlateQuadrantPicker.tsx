/**
 * PlateQuadrantPicker, visual picker for the column parity of the Echo source
 * plate a round is dispensed into.
 *
 * [source: kuma_core/kuro/plate_quadrant.py, read-only reference, not edited here]
 *
 * Two options (A1 = odd columns, A2 = even columns) plus "not specified". They
 * are laid out side by side, in the order the columns themselves run, so the
 * one fact that matters here can be seen rather than memorised from a caption:
 * a round is every other column, and forward and reverse primers are both
 * inside it, the reverse one row under its forward.
 * `usedQuadrants` renders as independent checkboxes because the plate is a
 * physical object this program never sees and a stale guess would be worse
 * than a checkbox list.
 */
import { useCallback, useId, useRef } from "react";
import type { KeyboardEvent } from "react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import type { EchoQuadrant } from "@/types/models";
// Geometry (the column parity, the legacy fold) lives in one module:
// EchoPlateView needs the same rule to shade the wells a run does not touch,
// and a second copy of a table that mirrors plate_quadrant.py would be a
// second thing to keep in step.
import { ECHO_QUADRANTS, quadrantColumnOffset } from "@/lib/echoQuadrant";

const GRID: readonly EchoQuadrant[] = ECHO_QUADRANTS;

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

  /** Arrow-key neighbour lookup over the two rounds plus the "none" row below
   *  them. Down from either round reaches "none"; up from "none" returns to A1
   *  (no column memory needed for two cells). */
  const neighbour = useCallback((from: Option, key: string): Option | null => {
    switch (key) {
      case "ArrowRight":
        return from === "A1" ? "A2" : null;
      case "ArrowLeft":
        return from === "A2" ? "A1" : null;
      case "ArrowDown":
        return from === "none" ? null : "none";
      case "ArrowUp":
        return from === "none" ? "A1" : null;
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

  const renderCell = (
    opt: Option,
    label: string,
    sublabel?: string,
    extraClassName?: string,
  ) => {
    const selected = current === opt;
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
          "flex h-11 flex-col items-center justify-center rounded-md border text-sm font-medium transition-colors",
          selected
            ? "border-primary bg-primary/10 text-foreground"
            : "border-border text-muted-foreground hover:bg-muted",
          extraClassName,
        )}
      >
        <span>{label}</span>
        {sublabel ? <span className="text-caption font-normal">{sublabel}</span> : null}
      </button>
    );
  };

  // 열 범위가 아니라 패리티다. "1-23" 이라고 적으면 사이 열까지 쓰는 것처럼
  // 읽히므로 홀수와 짝수를 그대로 말한다.
  const columnRange = (q: EchoQuadrant) =>
    t(
      quadrantColumnOffset(q) === 0
        ? "phaseC.export.all.quadrantColumnsOdd"
        : "phaseC.export.all.quadrantColumnsEven",
    );

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
        <div className="grid grid-cols-2 gap-1 w-52">
          {GRID.map((q) => renderCell(q, q, columnRange(q)))}
        </div>
        {renderCell(
          "none",
          t("phaseC.export.all.quadrantNone"),
          undefined,
          "w-52 h-9 text-caption",
        )}
      </div>
      <p className="text-caption text-muted-foreground">
        {t("phaseC.export.all.quadrantHelper")}
      </p>

      {/* 이미 소진된 round. plate 는 kuma 가 볼 수 없는 물건이라 작업자가 말한다.
          round 를 아직 안 골랐어도 소진 표시가 있으면 보여야 한다. v0.16.61 배치로
          저장된 프로젝트는 round 미선택 + 양쪽 소진 상태로 열리는데, 이때
          체크박스를 숨기면 작업자가 해제할 길이 없어 무엇을 골라도 거부된다. */}
      {(value !== null || usedQuadrants.length > 0) && (
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
