/**
 * WellSelectionPanel, which wells of the plate this campaign occupies.
 *
 * A campaign smaller than the plate leaves wells empty, and no input file says
 * which. Before this panel the run had no way to know, so an empty well was
 * scored as whatever the draft happened to place there, and reads leaking into
 * it from a neighbour looked like that variant.
 *
 * The panel draws the draft on the plate rather than offering an abstract
 * selector, because the point is to make the placement assumption visible: the
 * operator sees A1, B1, C1 going down the first column and can compare it with
 * the rack in front of them. Variant *i* goes to the *i*th selected well in
 * plate order, and that is the whole assignment rule. There is deliberately no
 * per-well variant editor: that is a sample map with a mouse, and the sample
 * map is what this replaces.
 *
 * Touching nothing sends nothing. The store keeps `selectedWells` at null until
 * the selection differs from the leading N+1 wells, so an operator who never
 * opens this panel gets exactly the run they got before it existed.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"

import { sendRequest } from "@/lib/ipc-mame"
import { formatError } from "@/lib/utils"
import { useMameAppStore } from "@/store/mame/mameAppStore"
import type { BuildWellLayoutResult, WellLayoutRow } from "@/types/mame/well_layout"
import {
  PLATE_CAPACITY,
  PLATE_COLS,
  PLATE_ROWS,
  PLATE_ROW_LABELS,
  allWellsInPlateOrder,
  leadingWells,
  sameWells,
  seqAt,
  sortWellsInPlateOrder,
  wellAt,
} from "@/lib/mame/wellSelection"

export function WellSelectionPanel() {
  const { t } = useTranslation()
  const expectedPath = useMameAppStore((s) => s.expectedPath)
  const variantSheet = useMameAppStore((s) => s.variantSheet)
  const variantColumn = useMameAppStore((s) => s.variantColumn)
  const selectedWells = useMameAppStore((s) => s.selectedWells)
  const setSelectedWells = useMameAppStore((s) => s.setSelectedWells)
  const setWellSelectionOccupants = useMameAppStore((s) => s.setWellSelectionOccupants)

  const [draft, setDraft] = useState<WellLayoutRow[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [focusSeq, setFocusSeq] = useState(1)
  const anchorSeq = useRef(1)
  const dragMode = useRef<"select" | "deselect" | null>(null)
  const gridRef = useRef<HTMLDivElement | null>(null)

  // The draft is read from the same RPC the run drafts its own layout with, so
  // what the grid shows and what the run places cannot disagree about a file.
  //
  // The occupant count goes into the store as well as into this component,
  // because the sidecar refuses a selection shorter than it and `selectCanRun`
  // is what has to know that. Drawing the warning here while the Run button
  // stayed enabled beside it was the whole defect.
  useEffect(() => {
    let alive = true
    if (!expectedPath) {
      setDraft(null)
      setLoadError(null)
      setWellSelectionOccupants(null)
      return () => {
        alive = false
      }
    }
    void (async () => {
      try {
        const result = await sendRequest<BuildWellLayoutResult>("build_well_layout", {
          expected_mutations_xlsx: expectedPath,
          variant_sheet: variantSheet ?? undefined,
          variant_column: variantColumn ?? undefined,
        })
        if (!alive) return
        setDraft(result.draft)
        setLoadError(null)
        setWellSelectionOccupants(result.draft.length)
      } catch (error) {
        if (!alive) return
        setDraft(null)
        setLoadError(formatError(error))
        // A count nobody could read is not a count. Left null so the gate falls
        // back to the one rule that holds without it: an empty declaration.
        setWellSelectionOccupants(null)
      }
    })()
    return () => {
      alive = false
    }
  }, [expectedPath, variantSheet, variantColumn, setWellSelectionOccupants])

  const occupants = draft ?? []
  const defaultSelection = useMemo(
    () => leadingWells(occupants.length),
    [occupants.length],
  )
  const selection = useMemo(
    () => (selectedWells ? sortWellsInPlateOrder(selectedWells) : defaultSelection),
    [selectedWells, defaultSelection],
  )
  const selectedSet = useMemo(() => new Set(selection), [selection])

  /** Which occupant, if any, sits in a given well under the current selection. */
  const occupantByWell = useMemo(() => {
    const map = new Map<string, string>()
    selection.forEach((well, index) => {
      const row = occupants[index]
      if (row) map.set(well, row.sample)
    })
    return map
  }, [selection, occupants])

  // Storing null for the default is what keeps an untouched panel invisible to
  // the run: the store only sends `selected_wells` when it is not null.
  const commit = useCallback(
    (next: Iterable<string>) => {
      const wells = sortWellsInPlateOrder(next)
      setSelectedWells(sameWells(wells, defaultSelection) ? null : wells)
    },
    [defaultSelection, setSelectedWells],
  )

  const applyTo = useCallback(
    (wells: string[], mode: "select" | "deselect") => {
      const next = new Set(selectedSet)
      for (const well of wells) {
        if (mode === "select") next.add(well)
        else next.delete(well)
      }
      commit(next)
    },
    [selectedSet, commit],
  )

  /**
   * A header covers its wells: all selected means clear them, anything else
   * means select them. Partial resolves to select, so one click never has to be
   * guessed at from how much of the row happened to be on.
   */
  const toggleGroup = useCallback(
    (wells: string[]) => {
      const allOn = wells.every((well) => selectedSet.has(well))
      applyTo(wells, allOn ? "deselect" : "select")
    },
    [selectedSet, applyTo],
  )

  const rowWells = useCallback(
    (row: number) => Array.from({ length: PLATE_COLS }, (_, col) => wellAt(row, col)),
    [],
  )
  const colWells = useCallback(
    (col: number) => Array.from({ length: PLATE_ROWS }, (_, row) => wellAt(row, col)),
    [],
  )

  // A drag paints the action its first well decided. Toggling each well as the
  // pointer crosses it flips wells back when a stroke doubles over itself,
  // which is the shape a hand makes on a small grid.
  const endDrag = useCallback(() => {
    dragMode.current = null
  }, [])
  useEffect(() => {
    window.addEventListener("pointerup", endDrag)
    window.addEventListener("pointercancel", endDrag)
    return () => {
      window.removeEventListener("pointerup", endDrag)
      window.removeEventListener("pointercancel", endDrag)
    }
  }, [endDrag])

  const onCellPointerDown = useCallback(
    (well: string, seq: number) => {
      const mode = selectedSet.has(well) ? "deselect" : "select"
      dragMode.current = mode
      anchorSeq.current = seq
      setFocusSeq(seq)
      applyTo([well], mode)
    },
    [selectedSet, applyTo],
  )

  const onCellPointerEnter = useCallback(
    (well: string) => {
      if (dragMode.current === null) return
      applyTo([well], dragMode.current)
    },
    [applyTo],
  )

  const focusCell = useCallback((seq: number) => {
    setFocusSeq(seq)
    const node = gridRef.current?.querySelector<HTMLElement>(`[data-seq="${seq}"]`)
    node?.focus()
  }, [])

  /**
   * Keyboard parity with the pointer, which the frontend charter makes a
   * release requirement rather than a nicety: arrows move, Space toggles,
   * Shift+arrow extends from the anchor. The extension runs over the plate
   * sequence, the same order the assignment rule uses, so a range selected by
   * keyboard and one dragged with the mouse produce the same list.
   */
  const onCellKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLButtonElement>, well: string, seq: number) => {
      const { row, col } = { row: (seq - 1) % PLATE_ROWS, col: Math.floor((seq - 1) / PLATE_ROWS) }
      let nextRow = row
      let nextCol = col
      switch (event.key) {
        case "ArrowUp":
          nextRow = Math.max(0, row - 1)
          break
        case "ArrowDown":
          nextRow = Math.min(PLATE_ROWS - 1, row + 1)
          break
        case "ArrowLeft":
          nextCol = Math.max(0, col - 1)
          break
        case "ArrowRight":
          nextCol = Math.min(PLATE_COLS - 1, col + 1)
          break
        case " ":
        case "Enter": {
          event.preventDefault()
          anchorSeq.current = seq
          applyTo([well], selectedSet.has(well) ? "deselect" : "select")
          return
        }
        default:
          return
      }
      event.preventDefault()
      const nextSeq = seqAt(nextRow, nextCol)
      if (event.shiftKey) {
        const from = Math.min(anchorSeq.current, nextSeq)
        const to = Math.max(anchorSeq.current, nextSeq)
        applyTo(allWellsInPlateOrder().slice(from - 1, to), "select")
      } else {
        anchorSeq.current = nextSeq
      }
      focusCell(nextSeq)
    },
    [applyTo, selectedSet, focusCell],
  )

  if (!expectedPath) return null

  return (
    <section
      className="rounded-lg border border-border bg-background p-4 space-y-3"
      aria-labelledby="mame-well-selection-heading"
    >
      <div className="space-y-1">
        <h3
          id="mame-well-selection-heading"
          className="text-body font-medium text-foreground"
        >
          {t("mame.wellSelection.title")}
        </h3>
        <p className="text-caption text-muted-foreground">
          {t("mame.wellSelection.description")}
        </p>
      </div>

      {loadError !== null && (
        <p className="text-caption text-error" role="status">
          {t("mame.wellSelection.loadFailed", { error: loadError })}
        </p>
      )}

      {draft !== null && (
        <>
          <p className="text-caption text-muted-foreground" aria-live="polite">
            {t("mame.wellSelection.counts", {
              selected: selection.length,
              occupants: occupants.length,
              capacity: PLATE_CAPACITY,
            })}
          </p>
          {selection.length < occupants.length && (
            <p className="text-caption text-error" role="alert">
              {t("mame.wellSelection.tooFewWells", {
                selected: selection.length,
                occupants: occupants.length,
              })}
            </p>
          )}

          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              className="rounded border border-border px-2 py-1 text-caption hover:bg-muted"
              onClick={() => commit(allWellsInPlateOrder())}
            >
              {t("mame.wellSelection.selectAll", { count: PLATE_CAPACITY })}
            </button>
            <button
              type="button"
              className="rounded border border-border px-2 py-1 text-caption hover:bg-muted"
              onClick={() => setSelectedWells(null)}
            >
              {t("mame.wellSelection.selectDefault", { count: occupants.length })}
            </button>
            {/*
              Clearing declares NO wells, which is deliberately not the same as
              declaring nothing: "Just the samples" above is the way back to the
              default (null, the leading wells). An empty declaration is a state
              the run cannot start from, and it holds the Run button through
              `selectCanRun` while the alert above says why. It used to build the
              same payload and leave Run enabled, so the sidecar refused it after
              the click and under an `expected:` label naming an innocent file.
            */}
            <button
              type="button"
              className="rounded border border-border px-2 py-1 text-caption hover:bg-muted"
              onClick={() => commit([])}
            >
              {t("mame.wellSelection.clearAll")}
            </button>
          </div>

          <div className="overflow-x-auto">
            <div
              ref={gridRef}
              role="grid"
              aria-label={t("mame.wellSelection.gridLabel")}
              aria-multiselectable="true"
              className="inline-grid gap-1"
              style={{ gridTemplateColumns: `2rem repeat(${PLATE_COLS}, 2.25rem)` }}
            >
              <div role="row" className="contents">
                <button
                  type="button"
                  role="columnheader"
                  className="rounded border border-border text-caption text-muted-foreground hover:bg-muted"
                  aria-label={t("mame.wellSelection.toggleAllLabel")}
                  onClick={() => toggleGroup(allWellsInPlateOrder())}
                >
                  {"◰"}
                </button>
                {Array.from({ length: PLATE_COLS }, (_, col) => (
                  <button
                    key={`col-${col}`}
                    type="button"
                    role="columnheader"
                    className="rounded border border-border py-0.5 text-caption text-muted-foreground hover:bg-muted"
                    aria-label={t("mame.wellSelection.toggleColumnLabel", {
                      column: col + 1,
                    })}
                    onClick={() => toggleGroup(colWells(col))}
                  >
                    {col + 1}
                  </button>
                ))}
              </div>

              {Array.from({ length: PLATE_ROWS }, (_, row) => (
                <div role="row" className="contents" key={`row-${row}`}>
                  <button
                    type="button"
                    role="rowheader"
                    className="rounded border border-border text-caption text-muted-foreground hover:bg-muted"
                    aria-label={t("mame.wellSelection.toggleRowLabel", {
                      row: PLATE_ROW_LABELS[row],
                    })}
                    onClick={() => toggleGroup(rowWells(row))}
                  >
                    {PLATE_ROW_LABELS[row]}
                  </button>
                  {Array.from({ length: PLATE_COLS }, (_, col) => {
                    const well = wellAt(row, col)
                    const seq = seqAt(row, col)
                    const isSelected = selectedSet.has(well)
                    const sample = occupantByWell.get(well)
                    return (
                      <button
                        key={well}
                        type="button"
                        role="gridcell"
                        data-seq={seq}
                        aria-selected={isSelected}
                        tabIndex={seq === focusSeq ? 0 : -1}
                        title={sample ? `${well} ${sample}` : well}
                        aria-label={
                          sample
                            ? t("mame.wellSelection.wellWithSample", { well, sample })
                            : t("mame.wellSelection.wellEmpty", { well })
                        }
                        onPointerDown={() => onCellPointerDown(well, seq)}
                        onPointerEnter={() => onCellPointerEnter(well)}
                        onKeyDown={(event) => onCellKeyDown(event, well, seq)}
                        onFocus={() => setFocusSeq(seq)}
                        className={[
                          "h-9 min-w-0 select-none overflow-hidden rounded border px-0.5 text-[10px] leading-tight",
                          isSelected
                            ? "border-primary bg-primary/10 text-foreground"
                            : "border-border bg-muted/30 text-muted-foreground",
                        ].join(" ")}
                      >
                        <span className="block truncate">{sample ?? ""}</span>
                      </button>
                    )
                  })}
                </div>
              ))}
            </div>
          </div>

          <p className="text-caption text-muted-foreground">
            {t("mame.wellSelection.keyboardHint")}
          </p>
        </>
      )}
    </section>
  )
}
