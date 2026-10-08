import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AppState } from "@/store/mame/mameAppStore";
import { ParameterPanel } from "./ParameterPanel";

// Mock i18n
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      const label = key.split(".").pop() ?? key;
      if (opts) {
        return `${label}(${Object.values(opts).join(",")})`;
      }
      return label;
    },
  }),
}));

// Mock mameAppStore
vi.mock("@/store/mame/mameAppStore");
import { useMameAppStore } from "@/store/mame/mameAppStore";

const BASE_RAW_RUN_PARAMS = {
  customBarcodesPath: "",
  sequencingSummaryPath: "",
  coverageFraction: 0.98,
  editDistRatio: 0.25,
  chimeraSplit: true,
  mapqThreshold: 25,
} as const;

/** Creates a minimal AppState partial for selector-based mock. */
function mockStore(overrides: Partial<AppState>) {
  vi.mocked(useMameAppStore).mockImplementation(
    (sel: (state: AppState) => unknown) =>
      sel({ rawRunParams: BASE_RAW_RUN_PARAMS, ...overrides } as AppState),
  );
}

describe("ParameterPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows Advanced section summary in raw_run mode", () => {
    mockStore({
      inputMode: "raw_run",
      mode: "amplicon",
      ingestMode: "barcode",
      cdsStart: 0,
      cdsEnd: 0,
      analyzeCdsCandidates: [],
      selectedAnalyzeCdsIndex: null,
      referencePath: "",
      minFileSizeKb: 50,
      minFilteredDepth: 15,
      manyCutoff: 5,
      distributionStats: null,
      isDemuxing: false,
      demuxProgress: 0,
      demuxMessage: "",
      demuxResult: null,
      ampliconLengthEstimate: null,
      setParams: vi.fn(),
      setSelectedAnalyzeCdsIndex: vi.fn(),
    });

    render(<ParameterPanel />);

    expect(screen.getByText(/advancedOptions/i)).toBeDefined();
  });

  it("does not render raw-run filters that the Run request cannot honor", () => {
    mockStore({
      inputMode: "raw_run",
      mode: "amplicon",
      ingestMode: "barcode",
      cdsStart: 0,
      cdsEnd: 0,
      analyzeCdsCandidates: [],
      selectedAnalyzeCdsIndex: null,
      referencePath: "",
      minFileSizeKb: 50,
      minFilteredDepth: 15,
      manyCutoff: 5,
      distributionStats: null,
      setParams: vi.fn(),
      setSelectedAnalyzeCdsIndex: vi.fn(),
    });

    render(<ParameterPanel />);

    expect(screen.queryByLabelText(/targetAmpliconLengthAriaLabel/i)).toBeNull();
    expect(screen.queryByLabelText(/lengthToleranceAriaLabel/i)).toBeNull();
    expect(screen.queryByText(/minQscore/i)).toBeNull();
    expect(screen.queryByRole("switch", { name: /normalizeHeadersAriaLabel/i })).toBeNull();
  });

  it("shows MAPQ alongside the advanced demux controls", async () => {
    mockStore({
      inputMode: "raw_run",
      mode: "amplicon",
      ingestMode: "barcode",
      cdsStart: 0,
      cdsEnd: 0,
      analyzeCdsCandidates: [],
      selectedAnalyzeCdsIndex: null,
      referencePath: "",
      minFileSizeKb: 50,
      minFilteredDepth: 15,
      manyCutoff: 5,
      distributionStats: null,
      isDemuxing: false,
      demuxProgress: 0,
      demuxMessage: "",
      demuxResult: null,
      ampliconLengthEstimate: null,
      setParams: vi.fn(),
      setSelectedAnalyzeCdsIndex: vi.fn(),
    });

    render(<ParameterPanel />);

    const summary = screen.getByText(/advancedOptions/i);
    await userEvent.click(summary);

    expect(screen.getByLabelText(/coverageFractionAriaLabel/i)).toBeDefined();
    expect(screen.getByLabelText(/mapqThresholdAriaLabel/i)).toBeDefined();
    expect(screen.getByLabelText(/editDistRatioAriaLabel/i)).toBeDefined();
    expect(screen.getByRole("switch", { name: /chimeraSplitAriaLabel/i })).toBeDefined();
  });

  it("shows the default MAPQ and sends an operator-selected value", async () => {
    const setParams = vi.fn();
    mockStore({
      inputMode: "raw_run",
      mode: "amplicon",
      ingestMode: "barcode",
      cdsStart: 0,
      cdsEnd: 0,
      analyzeCdsCandidates: [],
      selectedAnalyzeCdsIndex: null,
      referencePath: "",
      minFileSizeKb: 50,
      minFilteredDepth: 15,
      manyCutoff: 5,
      distributionStats: null,
      isDemuxing: false,
      demuxProgress: 0,
      demuxMessage: "",
      demuxResult: null,
      ampliconLengthEstimate: null,
      setParams,
      setSelectedAnalyzeCdsIndex: vi.fn(),
    });

    render(<ParameterPanel />);

    const summary = screen.getByText(/advancedOptions/i);
    await userEvent.click(summary);

    const coverageInput = screen.getByLabelText(/coverageFractionAriaLabel/i) as HTMLInputElement;
    expect(coverageInput.value).toBe("0.98");

    const editDistInput = screen.getByLabelText(/editDistRatioAriaLabel/i) as HTMLInputElement;
    expect(editDistInput.value).toBe("0.25");

    const mapqInput = screen.getByLabelText(/mapqThresholdAriaLabel/i) as HTMLInputElement;
    expect(mapqInput.value).toBe("25");
    fireEvent.change(mapqInput, { target: { value: "37" } });
    expect(setParams).toHaveBeenCalledWith({ rawRunParams: { mapqThreshold: 37 } });

    const chimeraSplit = screen.getByRole("switch", { name: /chimeraSplitAriaLabel/i });
    expect(chimeraSplit.getAttribute("aria-checked")).toBe("true");
  });

  it("refuses an edit-distance ratio the demux model rejects", async () => {
    // `DemuxParamsBase.edit_dist_ratio` is `gt=0.0` (`models.py:64`), so 0 is
    // the one value the model names illegal. The field used to clamp to
    // exactly that: the panel accepted it, the store kept it, and
    // `AnalyzeRawRunParams.model_validate` killed the run only after the demux
    // output dir was made and the FASTQ sampled.
    const setParams = vi.fn();
    mockStore({
      inputMode: "raw_run",
      mode: "amplicon",
      ingestMode: "barcode",
      cdsStart: 0,
      cdsEnd: 0,
      analyzeCdsCandidates: [],
      selectedAnalyzeCdsIndex: null,
      referencePath: "",
      minFileSizeKb: 50,
      minFilteredDepth: 15,
      manyCutoff: 5,
      distributionStats: null,
      isDemuxing: false,
      demuxProgress: 0,
      demuxMessage: "",
      demuxResult: null,
      ampliconLengthEstimate: null,
      setParams,
      setSelectedAnalyzeCdsIndex: vi.fn(),
    });

    render(<ParameterPanel />);
    await userEvent.click(screen.getByText(/advancedOptions/i));

    const editDistInput = screen.getByLabelText(/editDistRatioAriaLabel/i) as HTMLInputElement;
    // The browser's own guard, for the arrows and the validity state.
    expect(editDistInput.getAttribute("min")).toBe("0.01");

    // And the clamp behind it, for a typed value the arrows never produced.
    fireEvent.change(editDistInput, { target: { value: "0" } });
    expect(setParams).toHaveBeenCalledWith({ rawRunParams: { editDistRatio: 0.01 } });
  });

  it("shows ingest mode selector when inputMode is not raw_run", () => {
    mockStore({
      inputMode: "consensus",
      mode: "amplicon",
      ingestMode: "barcode",
      cdsStart: 0,
      cdsEnd: 0,
      analyzeCdsCandidates: [],
      selectedAnalyzeCdsIndex: null,
      referencePath: "",
      minFileSizeKb: 50,
      minFilteredDepth: 15,
      manyCutoff: 5,
      distributionStats: null,
      isDemuxing: false,
      demuxProgress: 0,
      demuxMessage: "",
      demuxResult: null,
      ampliconLengthEstimate: null,
      setParams: vi.fn(),
      setSelectedAnalyzeCdsIndex: vi.fn(),
    });

    render(<ParameterPanel />);

    expect(screen.queryByText(/ingest/i)).not.toBeNull();
  });
});
