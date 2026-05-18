// Adapter: dry-run RPC rows -> plate cell types for Echo/Janus preview.
// Assumptions:
// - Echo source plate is 384-well. Well code format "<RowLetter><2-digit col>" e.g. "A01".."P24".
// - Rows alternate fwd/rev: A(idx 0)=fwd, B(idx 1)=rev, ... P(idx 15)=rev. isFwd = rowIndex % 2 === 0.
// - Janus uses 96-well racks (A1..H12). Row's asp_rack value (1 or 2) determines target rack;
//   rack 1 = forward primer source, rack 2 = reverse primer source. Other asp_rack values are skipped.

export interface EchoCell {
  well: string;
  rowLetter: string;
  colNumber: number;
  isFwd: boolean;
  sourceWellName: string;
  destPlate: string;
  destWell: string;
  transferVolNl: number;
}

export interface JanusCell {
  well: string;
  rowLetter: string;
  colNumber: number;
  rack: 1 | 2;
  name: string;
  volumeUl: number;
}

export interface EchoDryRunRow {
  source_plate: string;
  source_well_name: string;
  source_well: string;
  dest_plate: string;
  dest_well_name: string;
  dest_well: string;
  transfer_vol: number;
}

export interface JanusDryRunRow {
  name: string;
  type: string;
  dsp_rack_label: string;
  no: number;
  asp_rack: number;
  asp_posi: string;
  dsp_rack: number;
  dsp_posi: string;
  volume: number;
}

function parseWell(code: string): { rowLetter: string; colNumber: number } {
  const match = /^([A-Pa-p])0*(\d+)$/.exec(code);
  if (!match) return { rowLetter: "", colNumber: 0 };
  return { rowLetter: match[1].toUpperCase(), colNumber: Number(match[2]) };
}

function rowIndex(letter: string): number {
  return letter.charCodeAt(0) - "A".charCodeAt(0);
}

export function adaptEchoRows(rows: EchoDryRunRow[]): EchoCell[] {
  return rows.map((r) => {
    const { rowLetter, colNumber } = parseWell(r.source_well);
    const idx = rowIndex(rowLetter);
    return {
      well: r.source_well,
      rowLetter,
      colNumber,
      isFwd: idx % 2 === 0,
      sourceWellName: r.source_well_name,
      destPlate: r.dest_plate,
      destWell: r.dest_well,
      transferVolNl: r.transfer_vol,
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
    if (r.asp_rack !== 1 && r.asp_rack !== 2) continue;
    const { rowLetter, colNumber } = parseWell(r.asp_posi);
    if (!rowLetter) continue;
    const cell: JanusCell = {
      well: r.asp_posi,
      rowLetter,
      colNumber,
      rack: r.asp_rack === 1 ? 1 : 2,
      name: r.name,
      volumeUl: r.volume,
    };
    if (r.asp_rack === 1) rack1.push(cell);
    else rack2.push(cell);
  }
  return { rack1, rack2 };
}
