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
 * the rack in front of them. The placement is the draft's own and clicking does
 * not move it: every variant keeps the well the plate order gave it, and the
 * selection says which of those wells this campaign actually filled. Leaving a
 * well out therefore drops what sits in it rather than pulling the next variant
 * up. There is deliberately no per-well variant editor: that is a sample map
 * with a mouse, and the sample map is what this replaces.
 *
 * Re-seating (variant *i* to the *i*th selected well) was the older rule, and
 * it made the grid rearrange itself under a click that was meant to describe
 * it: deselecting one well slid every later variant one well up.
 *
 * Touching nothing sends nothing. The store keeps `selectedWells` at null until
 * the selection differs from the leading N+1 wells, so an operator who never
 * opens this panel gets exactly the run they got before it existed.
 */

import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { save } from "@tauri-apps/plugin-dialog"
import { toast } from "sonner"

import { sendRequest } from "@/lib/ipc-mame"
import type { ExportBarcodeWorklistResult } from "@/types/mame/barcode_worklist"
import { formatError } from "@/lib/utils"
import { useMameAppStore } from "@/store/mame/mameAppStore"
import type { BuildWellLayoutResult, WellLayoutRow, WtPlacement } from "@/types/mame/well_layout"
import { NoControlWellNotice } from "@/components/mame/widgets/NoControlWellNotice"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
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

/**
 * How many excluded variants the notice names before it trails off. Six fits
 * the panel width; the count beside the list is what says how many there are,
 * so the tail costs nothing to leave out.
 */
const EXCLUDED_NAMES_SHOWN = 6

export function WellSelectionPanel() {
  const { t } = useTranslation()
  const expectedPath = useMameAppStore((s) => s.expectedPath)
  const variantSheet = useMameAppStore((s) => s.variantSheet)
  const variantColumn = useMameAppStore((s) => s.variantColumn)
  const selectedWells = useMameAppStore((s) => s.selectedWells)
  const setSelectedWells = useMameAppStore((s) => s.setSelectedWells)
  const wtPlacement = useMameAppStore((s) => s.wtPlacement)
  const setWtPlacement = useMameAppStore((s) => s.setWtPlacement)
  const setWtWell = useMameAppStore((s) => s.setWtWell)
  // For the seed NAMES on the worklist. Absent in consensus mode, where the
  // sheet still states every pairing because that comes from the plate.
  const customBarcodesPath = useMameAppStore((s) => s.rawRunParams.customBarcodesPath)
  const setWellSelectionOccupants = useMameAppStore((s) => s.setWellSelectionOccupants)

  const [draft, setDraft] = useState<WellLayoutRow[] | null>(null)
  // Variants the layout could not place at all, which is a different statement
  // from a well the operator chose to leave out: these have no well to leave.
  const [dropped, setDropped] = useState<string[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)
  const [focusSeq, setFocusSeq] = useState(1)
  const [exporting, setExporting] = useState(false)
  const wtPlacementId = useId()
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
      setDropped([])
      setLoadError(null)
      setWellSelectionOccupants(null)
      setWtWell(null)
      return () => {
        alive = false
      }
    }
    void (async () => {
      try {
        const result = await sendRequest<BuildWellLayoutResult>("mame.build_well_layout", {
          expected_mutations_xlsx: expectedPath,
          variant_sheet: variantSheet ?? undefined,
          variant_column: variantColumn ?? undefined,
          wt_placement: wtPlacement,
        })
        if (!alive) return
        setDraft(result.draft)
        setDropped(result.dropped_mutant_ids)
        setLoadError(null)
        setWellSelectionOccupants(result.draft.length)
        setWtWell(result.wt_well)
      } catch (error) {
        if (!alive) return
        setDraft(null)
        setDropped([])
        setLoadError(formatError(error))
        // A count nobody could read is not a count. Left null so the gate falls
        // back to the one rule that holds without it: an empty declaration.
        setWellSelectionOccupants(null)
        setWtWell(null)
      }
    })()
    return () => {
      alive = false
    }
  }, [
    expectedPath,
    variantSheet,
    variantColumn,
    wtPlacement,
    setWellSelectionOccupants,
    setWtWell,
  ])

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

  /**
   * Which occupant sits in a given well. Read straight off the draft, so it
   * does not depend on the selection and does not move when one is made.
   */
  const occupantByWell = useMemo(() => {
    const map = new Map<string, string>()
    for (const row of occupants) map.set(row.well, row.sample)
    return map
  }, [occupants])

  /** Draft occupants the current selection leaves off the plate, in plate order. */
  const excluded = useMemo(
    () => occupants.filter((row) => !selectedSet.has(row.well)),
    [occupants, selectedSet],
  )

  // Storing null for the default is what keeps an untouched panel invisible to
  // the run: the store only sends `selected_wells` when it is not null.
  const commit = useCallback(
    (next: Iterable<string>) => {
      const wells = sortWellsInPlateOrder(next)
      setSelectedWells(sameWells(wells, defaultSelection) ? null : wells)
    },
    [defaultSelection, setSelectedWells],
  )

  /**
   * Write the bench list: every occupied well, its ``{R}_{F}`` barcode and the
   * two seed primers that make it.
   *
   * Computed in the sidecar off the same two calls the run makes rather than
   * from the grid on screen, so the sheet cannot name a well the run would
   * score differently. `selectedWells` is sent as-is, null included: null means
   * the whole draft there exactly as it does on a run.
   */
  const exportWorklist = useCallback(async () => {
    if (!expectedPath) return
    setExporting(true)
    try {
      const target = await save({
        filters: [{ name: "CSV", extensions: ["csv"] }],
        defaultPath: "barcode_worklist.csv",
      })
      if (!target) return
      const result = await sendRequest<ExportBarcodeWorklistResult>(
        "mame.export_barcode_worklist",
        {
          expected_mutations_xlsx: expectedPath,
          variant_sheet: variantSheet ?? undefined,
          variant_column: variantColumn ?? undefined,
          custom_barcodes_xlsx: customBarcodesPath || undefined,
          selected_wells: selectedWells,
          // The same request this panel already sent to draw the grid, so the
          // sheet an operator pipettes from names the wells this grid drew
          // rather than the pre-2026-08-18 default.
          wt_placement: wtPlacement,
          output_path: target,
        },
      )
      toast.success(
        t("mame.wellSelection.worklistWritten", {
          rows: result.rows,
          reverse: result.reverse_indices.length,
          forward: result.forward_indices.length,
        }),
      )
      // A seed the workbook lacks is the one thing on that sheet an operator
      // cannot act on, so it is said separately rather than folded into a count.
      if (result.missing_seeds.length > 0) {
        toast.warning(
          t("mame.wellSelection.worklistMissingSeeds", {
            list: result.missing_seeds.join(", "),
          }),
        )
      }
    } catch (error) {
      toast.error(t("mame.wellSelection.worklistFailed", { error: formatError(error) }))
    } finally {
      setExporting(false)
    }
  }, [
    expectedPath,
    variantSheet,
    variantColumn,
    customBarcodesPath,
    selectedWells,
    wtPlacement,
    t,
  ])

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

      {/*
        Only meaningful for a row-order variant list: a file naming its own
        Well column states the control well itself and this choice is not
        consulted for it (kuma_core.mame.layout.build_draft_layout). Nothing
        the frontend reads today says which shape a given file is (see
        the `_suggest_column` gap this same change surfaced), so this stays
        enabled for every file rather than guessing.
      */}
      <div className="space-y-1">
        <Label htmlFor={wtPlacementId} className="text-caption font-medium">
          {t("mame.wellSelection.wtPlacement.label")}
        </Label>
        <Select
          value={wtPlacement}
          onValueChange={(value) => setWtPlacement(value as WtPlacement)}
        >
          <SelectTrigger id={wtPlacementId} className="h-7 w-full max-w-xs text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="last_well" className="text-xs">
              {t("mame.wellSelection.wtPlacement.lastWell")}
            </SelectItem>
            <SelectItem value="after_last_variant" className="text-xs">
              {t("mame.wellSelection.wtPlacement.afterLastVariant")}
            </SelectItem>
            <SelectItem value="none" className="text-xs">
              {t("mame.wellSelection.wtPlacement.none")}
            </SelectItem>
          </SelectContent>
        </Select>
        <p className="text-caption text-muted-foreground">
          {t("mame.wellSelection.wtPlacement.helper")}
        </p>
      </div>

      {loadError !== null && (
        <p className="text-caption text-error" role="status">
          {t("mame.wellSelection.loadFailed", { error: loadError })}
        </p>
      )}

      {/*
        An over-capacity list comes back as an empty layout with every name in
        dropped_mutant_ids, so the count below reads zero and the grid draws
        blank. Without this the screen states that there is nothing to place,
        which is the opposite of what happened.
      */}
      {dropped.length > 0 && (
        <p className="text-caption text-error" role="status">
          {t("mame.wellSelection.droppedVariants", {
            dropped: dropped.length,
            capacity: PLATE_CAPACITY,
            samples:
              dropped.slice(0, EXCLUDED_NAMES_SHOWN).join(", ") +
              (dropped.length > EXCLUDED_NAMES_SHOWN ? ", ..." : ""),
          })}
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
          <NoControlWellNotice />
          {/*
            Leaving a well out is a statement about the bench (that well was
            not filled), not a mistake, so this reports rather than blocks. It
            still has to be said out loud: the excluded variants get no verdict
            anywhere in the run, and the grid alone shows that only as absence.
          */}
          {excluded.length > 0 && (
            <p className="text-caption text-warning" role="status">
              {t("mame.wellSelection.excludedVariants", {
                excluded: excluded.length,
                samples:
                  excluded
                    .slice(0, EXCLUDED_NAMES_SHOWN)
                    .map((row) => `${row.sample} (${row.well})`)
                    .join(", ") +
                  (excluded.length > EXCLUDED_NAMES_SHOWN ? ", ..." : ""),
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
            {/*
              The bench list. Which wells a campaign fills decides which
              ``{R}_{F}`` barcodes it uses, and that pairing was stated nowhere
              an operator could read before pipetting: the package lists twenty
              primers with no plate in it, and the barcode column otherwise
              appears only on the workbook a finished run writes. Reading it off
              this grid by eye is the transcription step the grid exists to
              remove.
            */}
            <button
              type="button"
              disabled={exporting || selection.length === 0}
              className="rounded border border-border px-2 py-1 text-caption hover:bg-muted disabled:opacity-50"
              onClick={() => void exportWorklist()}
            >
              {t("mame.wellSelection.exportWorklist")}
            </button>
          </div>

          {/*
            Columns wide enough for a six-character mutant id on one line at
            10px. 2.25rem held about five and cut the rest, which on a grid
            whose whole job is showing WHICH variant sits WHERE is the one
            thing it must not do: R560E and R560Q both rendered as "R560..."
            and the two wells could not be told apart without hovering. The
            wrapper scrolls horizontally, so the extra width costs the layout
            nothing, and anything longer still wraps to a second line inside
            the cell rather than disappearing.
          */}
          <div className="overflow-x-auto">
            <div
              ref={gridRef}
              role="grid"
              aria-label={t("mame.wellSelection.gridLabel")}
              aria-multiselectable="true"
              className="inline-grid gap-1"
              style={{ gridTemplateColumns: `2rem repeat(${PLATE_COLS}, 3rem)` }}
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
                    // The control well, marked by more than colour: a ring
                    // (a box-shadow, so it layers over the selection border
                    // rather than fighting it for the same property) plus a
                    // symbol next to the "WT" text itself, for anyone who
                    // cannot tell the ring's colour from the selection one.
                    const isControlWell = sample === "WT"
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
                          isControlWell
                            ? t("mame.wellSelection.wellControl", { well })
                            : sample
                              ? t("mame.wellSelection.wellWithSample", { well, sample })
                              : t("mame.wellSelection.wellEmpty", { well })
                        }
                        onPointerDown={() => onCellPointerDown(well, seq)}
                        onPointerEnter={() => onCellPointerEnter(well)}
                        onKeyDown={(event) => onCellKeyDown(event, well, seq)}
                        onFocus={() => setFocusSeq(seq)}
                        className={[
                          // Two lines at 10px inside h-10, so a label the
                          // column cannot hold on one line wraps instead of
                          // being cut. `break-all` because these are
                          // identifiers with no spaces to break at: without it
                          // a long one overflows the cell rather than wrapping.
                          "flex h-10 min-w-0 items-center justify-center overflow-hidden rounded border px-0.5 text-[10px] leading-none",
                          isSelected
                            ? "border-primary bg-primary/10 text-foreground"
                            : sample
                              // Occupied but not declared: the draft put a
                              // variant here and the campaign says the well is
                              // empty, so the name stays visible and struck
                              // rather than vanishing into a blank cell.
                              ? "border-border bg-muted/30 text-muted-foreground line-through"
                              : "border-border bg-muted/30 text-muted-foreground",
                          isControlWell ? "ring-2 ring-ring ring-offset-1" : "",
                        ].join(" ")}
                      >
                        <span className="block break-all text-center">
                          {sample ?? ""}
                          {isControlWell && <span aria-hidden="true"> ✷</span>}
                        </span>
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
