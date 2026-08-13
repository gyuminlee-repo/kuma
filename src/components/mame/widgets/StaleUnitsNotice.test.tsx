import { describe, expect, it } from "vitest";
import { diagnoseStaleUnits } from "@/components/mame/widgets/StaleUnitsNotice";

describe("diagnoseStaleUnits", () => {
  it("says nothing when the folder made no membership claim", () => {
    // No run manifest: an externally sorted directory the user pointed MAME at
    // directly. Every subdirectory is meant to be read, so there is no such
    // thing as a leftover here and the notice must not appear.
    expect(diagnoseStaleUnits(null)).toBeNull();
  });

  it("says nothing when the folder was checked and is clean", () => {
    // A different statement from the case above, and both are silent on
    // screen. Keeping them distinct in the data is what stops a future reader
    // treating "no manifest" as "verified clean".
    expect(
      diagnoseStaleUnits({ names: [], run_dir: "/runs/260811", written_at: "t" }),
    ).toBeNull();
  });

  it("ignores empty names rather than rendering a blank row", () => {
    expect(
      diagnoseStaleUnits({ names: ["", ""], run_dir: "", written_at: "" }),
    ).toBeNull();
  });

  it("reports the plates the researcher run left behind", () => {
    // The 2026-08-10 case: barcodes 07, 08 and 09 were selected, and the export
    // folder still held three units of 14, 15 and 9 wells from the day before.
    // Six plates reached the verdict table and nothing said why.
    const names = diagnoseStaleUnits({
      names: ["sort_barcode15", "sort_barcode16", "sort_barcode17"],
      run_dir: "/runs/260810_khm",
      written_at: "2026-08-10T09:07:00Z",
    });
    expect(names).toEqual([
      "sort_barcode15",
      "sort_barcode16",
      "sort_barcode17",
    ]);
  });
});
