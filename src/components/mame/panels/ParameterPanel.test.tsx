import { render, screen } from "@testing-library/react";
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
  minQscore: 8.0,
  lengthMin: 800,
  lengthMax: 3000,
  targetLength: null,
  lengthToleranceBp: 30,
  normalizeHeaders: true,
  coverageFraction: 0.98,
  editDistRatio: 0.25,
  chimeraSplit: true,
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

  it("shows 3 new fields after expanding Advanced section", async () => {
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
    expect(screen.getByLabelText(/editDistRatioAriaLabel/i)).toBeDefined();
    expect(screen.getByRole("switch", { name: /chimeraSplitAriaLabel/i })).toBeDefined();
  });

  it("shows default values 0.98, 0.25, aria-checked=true after expanding Advanced", async () => {
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

    const coverageInput = screen.getByLabelText(/coverageFractionAriaLabel/i) as HTMLInputElement;
    expect(coverageInput.value).toBe("0.98");

    const editDistInput = screen.getByLabelText(/editDistRatioAriaLabel/i) as HTMLInputElement;
    expect(editDistInput.value).toBe("0.25");

    const chimeraSplit = screen.getByRole("switch", { name: /chimeraSplitAriaLabel/i });
    expect(chimeraSplit.getAttribute("aria-checked")).toBe("true");
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
