/**
 * Selection3DPanel — Current-Selection 3D Analysis panel.
 * Embedded in the KURO Output step view as a collapsible card,
 * collapsed by default to avoid eagerly loading 3Dmol.
 * [source: G002 panel spec]
 */

import { type ChangeEvent, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useShallow } from "zustand/react/shallow";
import type { AtomSpec, GLViewer, SelectionRange } from "3dmol";


import { useAppStore } from "@/store/appStore";
import { StateView } from "@/components/ui/StateView";
import {
  deriveSelectedPositions,
  selectedRefPositions,
  joinMappedYpred,
  type MappedYpredRow,
} from "@/lib/selection3d";
import type {
  ComputeDispersionResult,
  DomainInfo,
  FetchActiveSiteResult,
  SequenceInfo,
} from "@/types/models";

// ─── helpers ────────────────────────────────────────────────────────────────

function resolveRefSeq(seqInfo: SequenceInfo | null, selectedGene: string): string {
  if (!seqInfo) return "";
  const gene =
    seqInfo.genes.find((g) => String(g.cds_start) === selectedGene) ??
    seqInfo.genes[0];
  return gene?.translation ?? "";
}

function yPredColor(t: number): string {
  // t ∈ [0,1]: 0 = blue (#0000ff), 1 = red (#ff0000)
  const r = Math.round(t * 255).toString(16).padStart(2, "0");
  const b = Math.round((1 - t) * 255).toString(16).padStart(2, "0");
  return `#${r}00${b}`;
}

function normalizeT(yPred: number, minY: number, maxY: number): number {
  return maxY === minY ? 0.5 : Math.max(0, Math.min(1, (yPred - minY) / (maxY - minY)));
}

/** Extract CA b-factors (pLDDT proxy) from PDB text. Returns residue-number → b-factor map. */
function parseBFactors(pdbText: string): Map<number, number> {
  const map = new Map<number, number>();
  for (const line of pdbText.split("\n")) {
    if (!line.startsWith("ATOM") && !line.startsWith("HETATM")) continue;
    const atomName = line.slice(12, 16).trim();
    if (atomName !== "CA") continue;
    const resi = parseInt(line.slice(22, 26).trim(), 10);
    const b = parseFloat(line.slice(60, 66).trim());
    if (!isNaN(resi) && !isNaN(b) && !map.has(resi)) map.set(resi, b);
  }
  return map;
}

const DOMAIN_COLORS = [
  "#4e7ac7", "#e07b54", "#6dba6d", "#c974c4",
  "#d4a52a", "#7ecfcf", "#f0859b", "#a0a0f0",
];

// ─── subcomponents ──────────────────────────────────────────────────────────

function DispersionCard({ result }: { result: ComputeDispersionResult }) {
  const { t } = useTranslation();
  return (
    <div className="rounded border border-border bg-card p-3 text-sm" data-testid="dispersion-card">
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {t("selection3d.dispersionTitle")}
      </h3>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-0.5">
        <dt className="text-muted-foreground text-xs">{t("selection3d.dispersionMeanPairwise")}</dt>
        <dd className="font-semibold tabular-nums text-xs">{result.mean_pairwise.toFixed(2)} Å</dd>
        <dt className="text-muted-foreground text-xs">{t("selection3d.dispersionPercentile")}</dt>
        <dd className="font-semibold tabular-nums text-xs">{(result.percentile * 100).toFixed(1)}%</dd>
        <dt className="text-muted-foreground text-xs">{t("selection3d.dispersionClass")}</dt>
        <dd className="font-semibold text-xs">{result.klass}</dd>
        <dt className="text-muted-foreground text-xs">{t("selection3d.dispersionNullRange")}</dt>
        <dd className="tabular-nums text-muted-foreground text-xs">
          {result.null_p05.toFixed(1)}–{result.null_p95.toFixed(1)} Å
        </dd>
      </dl>
    </div>
  );
}

interface ActiveSiteControlProps {
  positions: number[];
  hasAnnotation: boolean;
  onAdd: (pos: number) => void;
  onRemove: (pos: number) => void;
}

function ActiveSiteControl({
  positions,
  hasAnnotation,
  onAdd,
  onRemove,
}: ActiveSiteControlProps) {
  const { t } = useTranslation();
  const [input, setInput] = useState("");

  function handleAdd() {
    const n = parseInt(input.trim(), 10);
    if (isNaN(n) || n <= 0) return;
    if (!positions.includes(n)) onAdd(n);
    setInput("");
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") handleAdd();
  }

  return (
    <div className="space-y-1.5" data-testid="active-site-control">
      {positions.length === 0 && !hasAnnotation && (
        <p className="text-xs italic text-muted-foreground">
          {t("selection3d.noActiveSiteAnnotation")}
        </p>
      )}
      <div className="flex flex-wrap gap-1">
        {positions.map((p) => (
          <span
            key={p}
            className="inline-flex items-center gap-0.5 rounded-full border border-border bg-muted px-2 py-0.5 text-xs"
          >
            {p}
            <button
              type="button"
              onClick={() => onRemove(p)}
              className="ml-0.5 text-muted-foreground hover:text-foreground"
              aria-label={`Remove position ${p}`}
            >
              ×
            </button>
          </span>
        ))}
      </div>
      <div className="flex gap-1">
        <input
          type="number"
          min={1}
          className="w-24 rounded border border-border bg-background px-2 py-0.5 text-xs"
          placeholder={t("selection3d.activeSiteAddPlaceholder")}
          value={input}
          onChange={(e: ChangeEvent<HTMLInputElement>) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          aria-label={t("selection3d.activeSiteAdd")}
        />
        <button
          type="button"
          onClick={handleAdd}
          className="rounded border border-border bg-muted px-2 py-0.5 text-xs hover:bg-accent"
        >
          {t("selection3d.activeSiteAddButton")}
        </button>
      </div>
    </div>
  );
}

interface PositionTableRow extends MappedYpredRow {
  isActiveSite: boolean;
  isInterface: boolean;
  plddt: number | null;
  domain: string;
}

function PositionTable({
  rows,
  onRowClick,
}: {
  rows: PositionTableRow[];
  onRowClick: (accPos: number) => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="max-h-48 overflow-auto rounded border border-border text-xs" data-testid="position-table">
      <table className="w-full border-collapse">
        <thead className="sticky top-0 bg-muted">
          <tr>
            {(
              [
                "colVariant",
                "colRefPos",
                "colAccPos",
                "colYPred",
                "colActiveSite",
                "colInterface",
                "colPlddt",
                "colDomain",
              ] as const
            ).map((k) => (
              <th
                key={k}
                className="border-b border-border px-2 py-1 text-left font-medium whitespace-nowrap"
              >
                {t(`selection3d.${k}`)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr
              key={`${row.variant}-${i}`}
              onClick={() => onRowClick(row.accPosition)}
              className="cursor-pointer hover:bg-accent/50"
              data-testid="position-row"
            >
              <td className="border-b border-border px-2 py-0.5 font-mono">{row.variant}</td>
              <td className="border-b border-border px-2 py-0.5 tabular-nums">{row.refPosition}</td>
              <td className="border-b border-border px-2 py-0.5 tabular-nums">{row.accPosition}</td>
              <td className="border-b border-border px-2 py-0.5 tabular-nums">{row.yPred.toFixed(3)}</td>
              <td className="border-b border-border px-2 py-0.5">
                {row.isActiveSite ? (
                  <span className="font-semibold text-success">✓</span>
                ) : (
                  <span className="text-muted-foreground">–</span>
                )}
              </td>
              <td className="border-b border-border px-2 py-0.5">
                {row.isInterface ? (
                  <span className="font-semibold text-info">✓</span>
                ) : (
                  <span className="text-muted-foreground">–</span>
                )}
              </td>
              <td className="border-b border-border px-2 py-0.5 tabular-nums">
                {row.plddt !== null ? row.plddt.toFixed(1) : "–"}
              </td>
              <td className="border-b border-border px-2 py-0.5 text-muted-foreground">
                {row.domain || "–"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DomainTable({
  rows,
  domains,
}: {
  rows: PositionTableRow[];
  domains: DomainInfo[];
}) {
  const { t } = useTranslation();
  const counts = domains
    .map((d) => ({
      name: d.name,
      count: rows.filter((r) => r.accPosition >= d.start && r.accPosition <= d.end).length,
    }))
    .filter((e) => e.count > 0);

  if (counts.length === 0) return null;

  return (
    <div className="max-h-32 overflow-auto rounded border border-border text-xs" data-testid="domain-table">
      <table className="w-full border-collapse">
        <thead className="sticky top-0 bg-muted">
          <tr>
            <th className="border-b border-border px-2 py-1 text-left font-medium">
              {t("selection3d.domainTableColDomain")}
            </th>
            <th className="border-b border-border px-2 py-1 text-left font-medium">
              {t("selection3d.domainTableColCount")}
            </th>
          </tr>
        </thead>
        <tbody>
          {counts.map((c) => (
            <tr key={c.name}>
              <td className="border-b border-border px-2 py-0.5">{c.name}</td>
              <td className="border-b border-border px-2 py-0.5 tabular-nums">{c.count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

type ColorMode = "domain" | "plddt" | "plain";

function ViewerToolbar({
  colorMode,
  onColorMode,
  showSurface,
  onSurfaceToggle,
  spin,
  onSpin,
  onReset,
  darkBg,
  onDarkBg,
  onFullscreen,
  onExportPng,
  showPlddt,
}: {
  colorMode: ColorMode;
  onColorMode: (m: ColorMode) => void;
  showSurface: boolean;
  onSurfaceToggle: () => void;
  spin: boolean;
  onSpin: () => void;
  onReset: () => void;
  darkBg: boolean;
  onDarkBg: () => void;
  onFullscreen: () => void;
  onExportPng: () => void;
  showPlddt: boolean;
}) {
  const { t } = useTranslation();

  const colorModes: ColorMode[] = showPlddt
    ? ["domain", "plddt", "plain"]
    : ["domain", "plain"];

  function btnCls(active: boolean) {
    return `rounded border px-2 py-0.5 text-xs ${
      active
        ? "border-primary bg-primary text-primary-foreground"
        : "border-border bg-background hover:bg-accent"
    }`;
  }

  function colorLabel(m: ColorMode) {
    if (m === "domain") return t("selection3d.colorDomain");
    if (m === "plddt") return t("selection3d.colorPlddt");
    return t("selection3d.colorPlain");
  }

  return (
    <div className="flex flex-wrap items-center gap-1 border-b border-border bg-muted/40 px-2 py-1" data-testid="viewer-toolbar">
      <span className="text-xs font-medium text-muted-foreground">{t("selection3d.colorMode")}:</span>
      {colorModes.map((m) => (
        <button key={m} type="button" onClick={() => onColorMode(m)} className={btnCls(colorMode === m)}>
          {colorLabel(m)}
        </button>
      ))}
      <span className="mx-0.5 h-3 w-px bg-border" />
      <button type="button" onClick={onSurfaceToggle} className={btnCls(showSurface)}>
        {t("selection3d.repSurface")}
      </button>
      <span className="mx-0.5 h-3 w-px bg-border" />
      <button type="button" onClick={onSpin} className={btnCls(spin)} data-testid="spin-btn">
        {t("selection3d.spin")}
      </button>
      <button
        type="button"
        onClick={onReset}
        className="rounded border border-border bg-background px-2 py-0.5 text-xs hover:bg-accent"
      >
        {t("selection3d.resetView")}
      </button>
      <button type="button" onClick={onDarkBg} className={btnCls(darkBg)}>
        {t("selection3d.darkBg")}
      </button>
      <button
        type="button"
        onClick={onFullscreen}
        className="rounded border border-border bg-background px-2 py-0.5 text-xs hover:bg-accent"
      >
        {t("selection3d.fullscreen")}
      </button>
      <button
        type="button"
        onClick={onExportPng}
        className="rounded border border-border bg-background px-2 py-0.5 text-xs hover:bg-accent"
        data-testid="export-png-btn"
      >
        {t("selection3d.exportPng")}
      </button>
    </div>
  );
}

// ─── main panel ─────────────────────────────────────────────────────────────

type ViewerPhase = "idle" | "loading" | "ready" | "error";

export function Selection3DPanel() {
  const { t } = useTranslation();

  const {
    structureAccession,
    uniprotAccession,
    seqInfo,
    selectedGene,
    evolveproSelectedVariants,
    evolveproRankedCandidates,
    yPredMap,
    domains,
    fetchPdbText,
    fetchActiveSite,
    computeDispersion,
  } = useAppStore(
    useShallow((s) => ({
      structureAccession: s.structureAccession,
      uniprotAccession: s.uniprotAccession,
      seqInfo: s.seqInfo,
      selectedGene: s.selectedGene,
      evolveproSelectedVariants: s.evolveproSelectedVariants,
      evolveproRankedCandidates: s.evolveproRankedCandidates,
      yPredMap: s.yPredMap,
      domains: s.domains,
      fetchPdbText: s.fetchPdbText,
      fetchActiveSite: s.fetchActiveSite,
      computeDispersion: s.computeDispersion,
    })),
  );

  const [open, setOpen] = useState(false);
  const [phase, setPhase] = useState<ViewerPhase>("idle");
  const [dispersion, setDispersion] = useState<ComputeDispersionResult | null>(null);
  const [activeSiteResult, setActiveSiteResult] = useState<FetchActiveSiteResult | null>(null);
  const [activeSitePositions, setActiveSitePositions] = useState<number[]>([]);
  const [showInterface, setShowInterface] = useState(true);
  const [colorMode, setColorMode] = useState<ColorMode>("domain");
  const [showSurface, setShowSurface] = useState(false);
  const [spin, setSpin] = useState(false);
  const [darkBg, setDarkBg] = useState(true);
  const [uploadSource, setUploadSource] = useState(false);
  const [uploadFileName, setUploadFileName] = useState<string | null>(null);
  const [droppedWarning, setDroppedWarning] = useState<string | null>(null);

  const containerRef = useRef<HTMLDivElement | null>(null);
  const viewerRef = useRef<GLViewer | null>(null);
  const bFactorMapRef = useRef<Map<number, number>>(new Map());
  const surfaceHandlerRef = useRef<number | null>(null);

  // Track accession loaded so we don't double-fetch on re-open
  const loadedAccessionRef = useRef<string>("");

  const accession = structureAccession || uniprotAccession;
  const disabled = !accession;

  // Derived at render time; stable for the current render cycle
  const rows = deriveSelectedPositions(
    evolveproSelectedVariants,
    evolveproRankedCandidates,
    yPredMap,
  );
  const joinResult =
    dispersion !== null
      ? joinMappedYpred(rows, dispersion.dropped, dispersion.mapped)
      : null;

  const activeSiteSet = new Set(activeSitePositions);
  const interfaceSet = new Set(activeSiteResult?.binding_positions ?? []);

  const tableRows: PositionTableRow[] = (joinResult?.rows ?? []).map((r) => {
    const dom = domains.find((d) => r.accPosition >= d.start && r.accPosition <= d.end);
    return {
      ...r,
      isActiveSite: activeSiteSet.has(r.accPosition),
      isInterface: interfaceSet.has(r.accPosition),
      plddt: bFactorMapRef.current.get(r.accPosition) ?? null,
      domain: dom?.name ?? "",
    };
  });

  // ─── load structure ─────────────────────────────────────────────────────
  useEffect(() => {
    if (!open || !accession) return;
    // Skip reload if same accession already loaded
    if (loadedAccessionRef.current === accession && phase !== "idle") return;

    let cancelled = false;
    const thisAccession = accession;

    async function load() {
      setPhase("loading");
      setDispersion(null);
      setDroppedWarning(null);
      setActiveSiteResult(null);
      setActiveSitePositions([]);
      surfaceHandlerRef.current = null;

      const currentRows = deriveSelectedPositions(
        evolveproSelectedVariants,
        evolveproRankedCandidates,
        yPredMap,
      );
      const positions = selectedRefPositions(currentRows);
      const refSeq = resolveRefSeq(seqInfo, selectedGene);

      const [pdbResult, activeSiteRes, dispersionRes] = await Promise.all([
        fetchPdbText(thisAccession),
        fetchActiveSite(thisAccession),
        positions.length > 0 && refSeq.length > 0
          ? computeDispersion({
              accession: thisAccession,
              refSeq,
              positions,
              seed: 0,
            })
          : Promise.resolve(null),
      ]);

      if (cancelled) return;

      // Active site
      if (activeSiteRes !== null) {
        setActiveSiteResult(activeSiteRes);
        setActiveSitePositions(activeSiteRes.active_site_positions);
      }

      // Dispersion
      if (dispersionRes !== null) {
        setDispersion(dispersionRes);
        const joined = joinMappedYpred(currentRows, dispersionRes.dropped, dispersionRes.mapped);
        const warnings: string[] = [];
        if (dispersionRes.dropped.length > 0) {
          warnings.push(
            t("selection3d.droppedWarning", {
              count: dispersionRes.dropped.length,
              positions: dispersionRes.dropped.join(", "),
            }),
          );
        }
        if (joined.lengthMismatch) {
          warnings.push(t("selection3d.lengthMismatch"));
        }
        setDroppedWarning(warnings.length > 0 ? warnings.join(" ") : null);
      }

      // PDB
      if (!pdbResult || !pdbResult.success || !pdbResult.pdb_text) {
        setPhase("error");
        return;
      }

      bFactorMapRef.current = parseBFactors(pdbResult.pdb_text);
      loadedAccessionRef.current = thisAccession;
      await initViewer(pdbResult.pdb_text, "pdb", cancelled);
    }

    void load();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, accession]);

  async function initViewer(text: string, format: string, cancelled: boolean) {
    const el = containerRef.current;
    if (!el || cancelled) {
      setPhase("error");
      return;
    }
    const $3Dmol = await import("3dmol");
    if (cancelled) return;
    const bgColor = darkBg ? "#1a1a1a" : "#f0f0f0";
    const viewer = $3Dmol.createViewer(el, { backgroundColor: bgColor });
    viewer.addModel(text, format);
    viewerRef.current = viewer;
    setPhase("ready");
  }

  // ─── effect: apply viewer styles (sync part) ────────────────────────────
  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer || phase !== "ready") return;

    // Base: gray cartoon
    viewer.setStyle({}, { cartoon: { color: "gray" } });

    // Color mode
    if (colorMode === "domain" && domains.length > 0) {
      domains.forEach((d, i) => {
        const color = DOMAIN_COLORS[i % DOMAIN_COLORS.length];
        viewer.setStyle({ resi: `${d.start}-${d.end}` as SelectionRange }, { cartoon: { color } });

      });
    } else if (colorMode === "plddt" && !uploadSource) {
      viewer.setStyle(
        {},
        {
          cartoon: {
            colorscheme: {
              prop: "b",
              gradient: "linear",
              min: 0,
              max: 100,
              colors: ["#FF7D45", "#FFDB13", "#65CBF3", "#0053D6"],
            },
          },
        },
      );
    }

    // Variant spheres (per-residue yPred gradient)
    if (joinResult !== null && joinResult.rows.length > 0) {
      const yPreds = joinResult.rows.map((r) => r.yPred);
      const minY = Math.min(...yPreds);
      const maxY = Math.max(...yPreds);
      for (const r of joinResult.rows) {
        const color = yPredColor(normalizeT(r.yPred, minY, maxY));
        viewer.addStyle(
          { resi: r.accPosition },
          { sphere: { color, radius: 1.0, opacity: 0.85 } },
        );
      }
    }

    // Active site sticks
    if (activeSitePositions.length > 0) {
      viewer.addStyle(
        { resi: activeSitePositions },

        { stick: { color: "#ff8800", radius: 0.2 } },
      );
    }

    // Interface: magenta spheres
    const bindingPositions = activeSiteResult?.binding_positions ?? [];
    if (showInterface && bindingPositions.length > 0) {
      viewer.addStyle(
        { resi: bindingPositions },

        { sphere: { color: "#d000d0", radius: 0.8, opacity: 0.7 } },
      );
    }

    // Hoverable: scoped to selected/active/interface residues
    const hoverSet = new Set<number>([
      ...(joinResult?.rows.map((r) => r.accPosition) ?? []),
      ...activeSitePositions,
      ...(showInterface ? bindingPositions : []),
    ]);
    if (hoverSet.size > 0) {
      const hoverSel = { resi: Array.from(hoverSet) };
      viewer.setHoverable(
        hoverSel,
        true,
        (atom: AtomSpec) => {
          const resi = atom.resi;
          const row = joinResult?.rows.find((r) => r.accPosition === resi);
          const parts: string[] = [`${atom.resn ?? ""}${resi ?? ""}`];
          if (row) parts.push(`${row.variant} y=${row.yPred.toFixed(3)}`);
          if (resi !== undefined && activeSiteSet.has(resi)) parts.push("active-site");
          if (resi !== undefined && interfaceSet.has(resi)) parts.push("interface");
          viewer.addLabel(parts.join(" | "), {
            backgroundColor: "rgba(0,0,0,0.7)",
            fontColor: "white",
            fontSize: 10,
          });
          viewer.render();
        },
        () => {
          viewer.removeAllLabels();
          viewer.render();
        },
      );
    }

    // Spin
    viewer.spin(spin);

    viewer.render();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, colorMode, activeSitePositions, showInterface, joinResult, domains, spin, uploadSource]);

  // ─── effect: surface (async) ─────────────────────────────────────────────
  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer || phase !== "ready") return;

    void (async () => {
      if (surfaceHandlerRef.current !== null) {
        viewer.removeSurface(surfaceHandlerRef.current);
        surfaceHandlerRef.current = null;
      }
      if (showSurface) {
        const $3Dmol = await import("3dmol");
        const handler = await viewer.addSurface($3Dmol.SurfaceType.VDW, {
          opacity: 0.7,
          color: "white",
        });
        surfaceHandlerRef.current = handler;
        viewer.render();
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, showSurface]);

  // ─── interaction handlers ───────────────────────────────────────────────
  function handleRowClick(accPos: number) {
    const viewer = viewerRef.current;
    if (!viewer) return;
    viewer.zoomTo({ resi: accPos }, 500);
    viewer.render();
  }

  function handleReset() {
    const viewer = viewerRef.current;
    if (!viewer) return;
    viewer.zoomTo({});
    viewer.render();
  }

  function handleFullscreen() {
    const el = containerRef.current?.parentElement ?? containerRef.current;
    if (!el) return;
    if (!document.fullscreenElement) {
      void el.requestFullscreen();
    } else {
      void document.exitFullscreen();
    }
  }

  function handleExportPng() {
    const viewer = viewerRef.current;
    if (!viewer) return;
    const uri = viewer.pngURI();
    const a = document.createElement("a");
    a.href = uri;
    a.download = `structure_${accession ?? "view"}.png`;
    a.click();
  }

  async function handleUpload(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const text = await file.text();
    const format = file.name.toLowerCase().endsWith(".cif") ? "cif" : "pdb";
    setUploadFileName(file.name);
    setUploadSource(true);
    setPhase("loading");
    bFactorMapRef.current = parseBFactors(text);
    loadedAccessionRef.current = ""; // force re-apply styles
    await initViewer(text, format, false);
  }

  // ─── render ──────────────────────────────────────────────────────────────
  return (
    <div className="mt-3 rounded border border-border bg-card" data-testid="selection3d-panel">
      {/* Collapsible header */}
      <button
        type="button"
        onClick={() => {
          if (!disabled) setOpen((v) => !v);
        }}
        className={`flex w-full items-center justify-between px-4 py-2.5 text-sm font-medium ${
          disabled ? "cursor-not-allowed opacity-50" : "hover:bg-accent/50"
        }`}
        aria-expanded={open}
        disabled={disabled}
        title={disabled ? t("selection3d.noAccession") : undefined}
        data-testid="panel-toggle"
      >
        <span>{t("selection3d.title")}</span>
        <span className="text-muted-foreground text-xs">{open ? "▲" : "▼"}</span>
      </button>

      {disabled && (
        <p className="px-4 pb-2 text-xs italic text-muted-foreground" data-testid="disabled-message">
          {t("selection3d.noAccession")}
        </p>
      )}

      {!disabled && open && (
        <div className="border-t border-border" data-testid="panel-body">
          {/* Upload fallback */}
          <div className="flex flex-wrap items-center gap-2 px-4 pt-2 text-xs">
            <span className="text-muted-foreground">{t("selection3d.uploadLabel")}:</span>
            <label className="cursor-pointer rounded border border-border bg-muted px-2 py-0.5 hover:bg-accent">
              {t("selection3d.uploadButton")}
              <input
                type="file"
                accept=".pdb,.cif"
                className="hidden"
                onChange={handleUpload}
                data-testid="upload-input"
              />
            </label>
            {uploadFileName !== null && (
              <span className="text-muted-foreground">{uploadFileName}</span>
            )}
            {uploadSource && (
              <span className="text-warning text-xs" data-testid="upload-source-note">
                {t("selection3d.uploadSourceNote")}
              </span>
            )}
          </div>

          {/* Dropped-positions warning */}
          {droppedWarning !== null && (
            <div
              className="mx-4 mt-2 rounded border border-warning/40 bg-warning/10 px-3 py-2 text-xs text-warning"
              data-testid="dropped-warning"
            >
              {droppedWarning}
            </div>
          )}

          {/* Loading overlay (viewer container is still rendered below) */}
          {phase === "loading" && (
            <div className="flex h-48 items-center justify-center" data-testid="loading-state">
              <StateView variant="loading" title={t("selection3d.loading")} />
            </div>
          )}

          {/* Error state */}
          {phase === "error" && (
            <div className="flex h-48 items-center justify-center" data-testid="error-state">
              <StateView
                variant="empty"
                title={t("selection3d.noStructure")}
                description={t("selection3d.noStructureDesc")}
              />
            </div>
          )}

          {/* Always render viewer container + controls so containerRef stays mounted */}
          <div className={phase === "loading" || phase === "error" ? "hidden" : "space-y-3 p-4"}>
            {phase === "ready" && (
              <>
                <ViewerToolbar
                  colorMode={colorMode}
                  onColorMode={setColorMode}
                  showSurface={showSurface}
                  onSurfaceToggle={() => setShowSurface((v) => !v)}
                  spin={spin}
                  onSpin={() => setSpin((v) => !v)}
                  onReset={handleReset}
                  darkBg={darkBg}
                  onDarkBg={() => setDarkBg((v) => !v)}
                  onFullscreen={handleFullscreen}
                  onExportPng={handleExportPng}
                  showPlddt={!uploadSource}
                />
                {/* Interface toggle */}
                <div className="flex flex-wrap gap-3 px-1 text-xs">
                  <label className="flex cursor-pointer items-center gap-1.5">
                    <input
                      type="checkbox"
                      checked={showInterface}
                      onChange={(e) => setShowInterface(e.target.checked)}
                      className="accent-primary"
                      data-testid="interface-toggle"
                    />
                    <span className="inline-block h-2.5 w-2.5 rounded-full bg-purple-500" />
                    {t("selection3d.interface")}
                  </label>
                </div>
              </>
            )}

            {/* 3Dmol viewer container — always mounted so containerRef is valid */}
            <div
              ref={containerRef}
              className="relative h-72 w-full rounded border border-border"
              data-testid="viewer-container"
            />

            {phase === "ready" && (
              <>
                {/* Active site control */}
                <div>
                  <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    {t("selection3d.activeSite")}
                  </h3>
                  <ActiveSiteControl
                    positions={activeSitePositions}
                    hasAnnotation={activeSiteResult?.has_annotation ?? false}
                    onAdd={(p) =>
                      setActiveSitePositions((prev) =>
                        [...prev, p].sort((a, b) => a - b),
                      )
                    }
                    onRemove={(p) =>
                      setActiveSitePositions((prev) => prev.filter((x) => x !== p))
                    }
                  />
                </div>

                {/* Dispersion card */}
                {dispersion !== null && <DispersionCard result={dispersion} />}

                {/* Position table */}
                {tableRows.length > 0 && (
                  <div>
                    <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      {t("selection3d.positionTableTitle")}
                    </h3>
                    <PositionTable rows={tableRows} onRowClick={handleRowClick} />
                  </div>
                )}

                {/* Domain table */}
                {domains.length > 0 && tableRows.length > 0 && (
                  <div>
                    <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      {t("selection3d.domainTableTitle")}
                    </h3>
                    <DomainTable rows={tableRows} domains={domains} />
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
