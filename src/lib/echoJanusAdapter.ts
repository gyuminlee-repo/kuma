// Adapter: dry-run RPC rows -> plate cell types for Echo/Janus preview.
// Assumptions:
// - Echo source plate is 384-well. Well code format "<RowLetter><2-digit col>" e.g. "A01".."P24".
// - Rows alternate fwd/rev: A(idx 0)=fwd, B(idx 1)=rev, ... P(idx 15)=rev. isFwd = rowIndex % 2 === 0.
// - Janus uses 96-well racks (A1..H12). Direction comes from the row's `role`
//   field ("fwd"/"rev"), which the sidecar states outright; the rack fields hold
//   plate names set by deck policy and are not read as a direction marker. A row
//   whose direction is not stated is skipped.
// - Dest mapping: rows are grouped by `mutation` to form a 96-well destination cell.
//   Both Echo and Janus dry-run rows carry `mutation` directly from the sidecar (Phase 1/2).

export interface EchoCell {
  well: string;
  rowLetter: string;
  colNumber: number;
  isFwd: boolean;
  sourceWellName: string;
  destPlate: string;
  destWell: string;
  transferVolNl: number;
  mutation: string;
}

export interface JanusCell {
  well: string;
  rowLetter: string;
  colNumber: number;
  /**
   * Which of the two preview panels the cell belongs to: 1 = forward source,
   * 2 = reverse source. A panel index, not the deck plate the instrument
   * aspirates from; that plate is named on the source row (`asp_rack`).
   */
  rack: 1 | 2;
  name: string;
  volumeUl: number;
  mutation: string;
}

export interface DestCell {
  well: string;
  rowLetter: string;
  colNumber: number;
  mutation: string;
  hasF: boolean;
  hasR: boolean;
  fwdVol?: number;
  revVol?: number;
  fwdSource?: string;
  revSource?: string;
}

export interface EchoDryRunRow {
  source_plate: string;
  source_well_name: string;
  source_well: string;
  dest_plate: string;
  dest_well_name: string;
  dest_well: string;
  transfer_vol: number;
  mutation: string;
}

/**
 * Direction of a transfer, as the sidecar states it. The only way this preview
 * learns whether a row is a forward or a reverse transfer.
 */
export type JanusRole = "fwd" | "rev";

/**
 * One row of the JANUS dry-run payload, field for field with the dicts
 * `build_janus_rows` returns (`kuma_core/kuro/plate_mapper.py`), which
 * `_build_janus_preview_rows` passes through untouched
 * (`python-core/sidecar_kuro/handlers/export.py`).
 *
 * The first eight fields are the instrument sheet columns, in
 * `JANUS_DEVICE_HEADER` order (`kuma_core/shared/janus_deck.py`); `mutation`
 * and `role` ride along for the UI and are never written to a file.
 */
export interface JanusDryRunRow {
  name: string;
  type: string;
  no: number;
  /**
   * `Asp. Rack`: the NAME of the source plate ("fw plate", "rv plate", or a
   * name a MAME run generated), not a deck slot number. Deck policy, never a
   * direction marker.
   */
  asp_rack: string;
  asp_posi: string;
  /** `Dsp. Rack`: the name of the destination plate, e.g. "PCR mixture plate". */
  dsp_rack: string;
  dsp_posi: string;
  volume: number;
  mutation: string;
  /**
   * Direction of the transfer, stated by the sidecar (`build_janus_rows`, which
   * always sets it). Optional so that a payload missing it still parses; such a
   * row is skipped rather than guessed at. See {@link janusRole}.
   */
  role?: JanusRole;
}

/**
 * Direction of a Janus row.
 *
 * `role` is the only source: the sidecar states the direction, so relabelling
 * the deck cannot flip F/R in the preview. Nothing else on the row carries the
 * direction. `Asp. Rack` holds a plate name chosen by deck policy, so there is
 * no value left to compare against. `null` means the direction was not stated
 * and the row is left out rather than guessed.
 */
export function janusRole(row: JanusDryRunRow): JanusRole | null {
  if (row.role === "fwd" || row.role === "rev") return row.role;
  return null;
}

function parseWell(code: string): { rowLetter: string; colNumber: number } {
  const match = /^([A-Pa-p])0*(\d+)$/.exec(code);
  if (!match) return { rowLetter: "", colNumber: 0 };
  return { rowLetter: match[1].toUpperCase(), colNumber: Number(match[2]) };
}

function rowIndex(letter: string): number {
  return letter.charCodeAt(0) - "A".charCodeAt(0);
}

/**
 * Parse a Janus row `name` like `"M1A-F"` or `"M1A-R"` into mutation + tag.
 * Matches Phase 1 suffix policy (`-F`/`-R`). Legacy `-fw`/`-rv` no longer recognized.
 * Returns `tag: null` if no recognized suffix.
 */
export function parseJanusName(name: string): {
  mutation: string;
  tag: "F" | "R" | null;
} {
  // Split on last "-" so mutations containing "-" survive (rare but possible).
  const idx = name.lastIndexOf("-");
  if (idx <= 0) return { mutation: name, tag: null };
  const mut = name.slice(0, idx);
  const side = name.slice(idx + 1);
  if (side === "F") return { mutation: mut, tag: "F" };
  if (side === "R") return { mutation: mut, tag: "R" };
  return { mutation: name, tag: null };
}

export function adaptEchoRows(rows: EchoDryRunRow[]): EchoCell[] {
  return rows.map((r) => {
    const { rowLetter, colNumber } = parseWell(r.source_well);
    const idx = rowIndex(rowLetter);
    return {
      well: rowLetter && colNumber > 0 ? `${rowLetter}${String(colNumber).padStart(2, "0")}` : r.source_well,
      rowLetter,
      colNumber,
      isFwd: idx % 2 === 0,
      sourceWellName: r.source_well_name,
      destPlate: r.dest_plate,
      destWell: r.dest_well,
      transferVolNl: r.transfer_vol,
      mutation: r.mutation,
    };
  });
}

export function adaptJanusRows(rows: JanusDryRunRow[]): {
  rack1: JanusCell[];
  rack2: JanusCell[];
} {
  const rack1: JanusCell[] = [];
  const rack2: JanusCell[] = [];
  for (const r of rows) {
    const role = janusRole(r);
    if (role === null) continue;
    const { rowLetter, colNumber } = parseWell(r.asp_posi);
    if (!rowLetter) continue;
    // The two returned arrays are the forward and reverse source panels, so
    // membership follows the direction, not the deck number. `rack` repeats the
    // panel index for the view's grid key.
    const cell: JanusCell = {
      well: r.asp_posi,
      rowLetter,
      colNumber,
      rack: role === "fwd" ? 1 : 2,
      name: r.name,
      volumeUl: r.volume,
      mutation: r.mutation,
    };
    if (role === "fwd") rack1.push(cell);
    else rack2.push(cell);
  }
  return { rack1, rack2 };
}

// --- Dest cell adapters ----------------------------------------------------
// Both Echo and Janus output rows describe transfers from a source well into
// a 96-well destination PCR plate. UI dest preview groups by `mutation` and
// reports whether F/R have both arrived.

function ensureDest(
  map: Map<string, DestCell>,
  mutation: string,
  well: string,
): DestCell {
  const existing = map.get(mutation);
  if (existing) return existing;
  const { rowLetter, colNumber } = parseWell(well);
  const cell: DestCell = {
    well,
    rowLetter,
    colNumber,
    mutation,
    hasF: false,
    hasR: false,
  };
  map.set(mutation, cell);
  return cell;
}

/**
 * Build a `DestCell[]` from Echo dry-run rows. Groups by `mutation`.
 * Echo rows distinguish fwd/rev via 384-well source row parity (A,C,E,...=fwd).
 */
export function adaptDestCellsEcho(rows: EchoDryRunRow[]): DestCell[] {
  const map = new Map<string, DestCell>();
  for (const r of rows) {
    if (!r.mutation) continue;
    const cell = ensureDest(map, r.mutation, r.dest_well);
    const { rowLetter } = parseWell(r.source_well);
    const isFwd = rowLetter ? rowIndex(rowLetter) % 2 === 0 : false;
    if (isFwd) {
      cell.hasF = true;
      cell.fwdVol = r.transfer_vol;
      cell.fwdSource = r.source_well_name;
    } else {
      cell.hasR = true;
      cell.revVol = r.transfer_vol;
      cell.revSource = r.source_well_name;
    }
  }
  return Array.from(map.values());
}

/**
 * Build a `DestCell[]` from Janus dry-run rows. Groups by `mutation`.
 * Janus rows distinguish fwd/rev via {@link janusRole}.
 */
export function adaptDestCellsJanus(rows: JanusDryRunRow[]): DestCell[] {
  const map = new Map<string, DestCell>();
  for (const r of rows) {
    if (!r.mutation) continue;
    const role = janusRole(r);
    if (role === null) continue;
    const cell = ensureDest(map, r.mutation, r.dsp_posi);
    if (role === "fwd") {
      cell.hasF = true;
      cell.fwdVol = r.volume;
      cell.fwdSource = r.asp_posi;
    } else {
      cell.hasR = true;
      cell.revVol = r.volume;
      cell.revSource = r.asp_posi;
    }
  }
  return Array.from(map.values());
}
