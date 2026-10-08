import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import en from "@/locales/en.json";
import ko from "@/locales/ko.json";
import { createInstance } from "i18next";
import { I18nextProvider } from "react-i18next";
import type { WellEntry } from "@/types/mame/models";

vi.mock("@/lib/ipc-mame", () => ({
  sendRequest: vi.fn(), setProgressHandler: vi.fn(), cancelAndRespawn: vi.fn(),
}));

import { useMameAppStore } from "@/store/mame/mameAppStore";
import { detectFailClusters, PlateClusterAlert } from "./PlateClusterAlert";

function well(position: string, verdict: WellEntry["verdict"] = "LOWDEPTH", nativeBarcode = "barcode01"): WellEntry {
  return { well: position, verdict, native_barcode: nativeBarcode, barcode: "1_1", mutant_id: position,
    selected: false, notes: "", is_fallback: false, fallback_reason: null };
}

beforeEach(() => useMameAppStore.setState({ wells: [] }));

describe("detectFailClusters", () => {
  it("requires three contiguous wells in a row, accepting both low depth and no call", () => {
    expect(detectFailClusters([well("B3"), well("B04", "NO_CALL")])).toEqual([]);
    expect(detectFailClusters([well("B5"), well("B3"), well("B04", "NO_CALL")])).toEqual([
      { nativeBarcode: "barcode01", direction: "row", wells: ["B03", "B04", "B05"] },
    ]);
  });

  it("detects a vertical run separately from a horizontal run", () => {
    expect(detectFailClusters([well("F12"), well("G12", "NO_CALL"), well("H12")])).toEqual([
      { nativeBarcode: "barcode01", direction: "column", wells: ["F12", "G12", "H12"] },
    ]);
  });

  it("does not connect diagonal wells, gaps, or row boundaries", () => {
    expect(detectFailClusters([well("A1"), well("B2"), well("C3")])).toEqual([]);
    expect(detectFailClusters([well("A1"), well("A2"), well("A4")])).toEqual([]);
    expect(detectFailClusters([well("A11"), well("A12"), well("B1")])).toEqual([]);
  });

  it("groups native barcodes before coordinates and never invents a cross-plate run", () => {
    expect(detectFailClusters([
      well("A1", "LOWDEPTH", "barcode01"), well("A2", "LOWDEPTH", "barcode02"),
      well("A3", "NO_CALL", "barcode03"),
    ])).toEqual([]);
    expect(detectFailClusters([
      ...["A1", "A2", "A3"].map((w) => well(w, "LOWDEPTH", "barcode01")),
      ...["A1", "A2", "A3"].map((w) => well(w, "NO_CALL", "barcode02")),
    ]).map((c) => c.nativeBarcode)).toEqual(["barcode01", "barcode02"]);
  });

  it("does not infer a plate for empty, whitespace, missing, or null barcodes", () => {
    for (const barcode of ["", "  ", undefined, null]) {
      const unknown = ["A1", "A2", "A3"].map((w) => ({ ...well(w), native_barcode: barcode })) as unknown as WellEntry[];
      expect(detectFailClusters(unknown)).toEqual([]);
      expect(detectFailClusters([well("A1"), well("A2"), unknown[2]])).toEqual([]);
    }
  });

  it.each(["PASS", "AMBIGUOUS", "FRAMESHIFT", "MANY", "WRONG_AA", "MIXED"] as const)(
    "excludes %s even when adjacent to low-depth wells", (verdict) => {
      expect(detectFailClusters([well("A1"), well("A2", verdict), well("A3")])).toEqual([]);
      expect(detectFailClusters([well("A1", verdict), well("A2", verdict), well("A3", verdict)])).toEqual([]);
    },
  );

  it("rejects invalid coordinates without repairing or partially parsing them", () => {
    const invalid = ["A0", "A00", "A13", "I1", "A001", "A1x", "1A", "A1.0", "A+1", "A-1", "", "A 1"];
    for (const position of invalid) {
      expect(detectFailClusters([well("A1"), well("A2"), well(position)])).toEqual([]);
    }
  });

  it("deduplicates positions and emits maximal, separate runs", () => {
    expect(detectFailClusters([well("A1"), well("A01"), well("A2")])).toEqual([]);
    expect(detectFailClusters([1, 2, 3, 4, 6, 7, 8].map((c) => well(`A${c}`))).map((c) => c.wells)).toEqual([
      ["A01", "A02", "A03", "A04"], ["A06", "A07", "A08"],
    ]);
  });

  it("handles all 96 wells per plate without merging identical positions across plates", () => {
    const full = (nb: string) => Array.from({ length: 96 }, (_, i) =>
      well(`${String.fromCharCode(65 + Math.floor(i / 12))}${i % 12 + 1}`, i % 2 ? "NO_CALL" : "LOWDEPTH", nb));
    const clusters = detectFailClusters([...full("barcode01"), ...full("barcode02")]);
    expect(clusters).toHaveLength(40);
    for (const nb of ["barcode01", "barcode02"]) {
      const plate = clusters.filter((c) => c.nativeBarcode === nb);
      expect(plate.filter((c) => c.direction === "row")).toHaveLength(8);
      expect(plate.filter((c) => c.direction === "column")).toHaveLength(12);
      expect(plate.filter((c) => c.direction === "row").every((c) => c.wells.length === 12)).toBe(true);
      expect(plate.filter((c) => c.direction === "column").every((c) => c.wells.length === 8)).toBe(true);
    }
  });

  it("handles an empty run", () => expect(detectFailClusters([])).toEqual([]));
});

describe("PlateClusterAlert", () => {
  it("shows no notice for an empty run or an isolated pair", () => {
    const { rerender } = render(<PlateClusterAlert />);
    expect(screen.queryByRole("note")).toBeNull();
    useMameAppStore.setState({ wells: [well("A1"), well("A2")] });
    rerender(<PlateClusterAlert />);
    expect(screen.queryByRole("note")).toBeNull();
  });

  it("localizes the cautious history hint in Korean", async () => {
    const i18n = createInstance();
    await i18n.init({ lng: "ko", resources: { ko: { translation: ko } }, interpolation: { escapeValue: false } });
    useMameAppStore.setState({ wells: [well("B3"), well("B4"), well("B5")] });
    render(<I18nextProvider i18n={i18n}><PlateClusterAlert /></I18nextProvider>);
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByRole("note")).toHaveTextContent("분주 이력을 확인해 보세요");
    expect(screen.getByRole("note")).toHaveTextContent("이 패턴만으로 원인을 단정할 수는 없습니다");
    expect(screen.getByRole("note")).toHaveTextContent("barcode01");
  });

  it("starts collapsed and identifies the source plate with a non-causal history hint", () => {
    useMameAppStore.setState({ wells: [well("B3"), well("B4"), well("B5")] });
    render(<PlateClusterAlert />);
    const disclosure = screen.getByRole("button");
    expect(disclosure).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText(/pipetting history/i)).toBeNull();
    fireEvent.click(disclosure);
    expect(disclosure).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("note", { name: en.mame.qc.plate.clusterAlertAriaLabel })).toHaveTextContent("barcode01");
    expect(screen.getByRole("note")).toHaveTextContent("B03-B05");
    expect(screen.getByRole("note")).toHaveTextContent("does not establish the cause");
    expect(screen.queryByRole("alert")).toBeNull();
    fireEvent.click(disclosure);
    expect(screen.queryByText(/pipetting history/i)).toBeNull();
  });
});
