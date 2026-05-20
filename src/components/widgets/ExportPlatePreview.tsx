import { useEffect, useMemo, useState, useCallback, useRef } from "react";
import { useTranslation } from "react-i18next";
import { useShallow } from "zustand/react/shallow";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { rpc } from "@/lib/ipc";
import {
  adaptEchoRows,
  adaptJanusRows,
  adaptDestCellsEcho,
  adaptDestCellsJanus,
  type EchoCell,
  type JanusCell,
  type DestCell,
  type EchoDryRunRow,
  type JanusDryRunRow,
} from "@/lib/echoJanusAdapter";
import { EchoPlateView } from "./EchoPlateView";
import { JanusPlateView } from "./JanusPlateView";
import { DestPlateView } from "./DestPlateView";
import { PlateLegendsPanel } from "./PlateLegendsPanel";
import { useAppStore } from "@/store/appStore";
import { getSortedMutations, reorderMappings } from "@/lib/plate-utils";
import type { MappingRange } from "@/types/models.generated";

interface EchoDryRunResult {
  rows: EchoDryRunRow[];
  total: number;
  transfer_vol: number;
}

interface JanusDryRunResult {
  rows: JanusDryRunRow[];
  total: number;
  transfer_vol: number;
}

type View = "echo" | "janus";

// 16-row labels for 384-well source plate mapping range selector.
const ROW_LETTERS = [
  "A", "B", "C", "D", "E", "F", "G", "H",
  "I", "J", "K", "L", "M", "N", "O", "P",
] as const;

/**
 * ExportPlatePreview
 *
 * Container widget that fetches Echo + JANUS mapping dry-run rows from the
 * Kuro sidecar on mount, adapts them via echoJanusAdapter, and renders the
 * 384-well Echo plate or 96-well JANUS racks under a Tabs switcher. Echo
 * and JANUS are mutually exclusive views (never rendered simultaneously).
 *
 * Note: the design plan referenced a shadcn ToggleGroup primitive. That
 * primitive is not installed in this repo; the Tabs primitive
 * (`@/components/ui/tabs`) is semantically equivalent (single-select,
 * exclusive content, ARIA-correct) and avoids adding a new dependency.
 */
export function ExportPlatePreview() {
  const { t } = useTranslation();
  const [view, setView] = useState<View>("echo");
  const [echo, setEcho] = useState<EchoCell[]>([]);
  const [echoDest, setEchoDest] = useState<DestCell[]>([]);
  const [janus, setJanus] = useState<{ rack1: JanusCell[]; rack2: JanusCell[] }>({
    rack1: [],
    rack2: [],
  });
  const [janusDest, setJanusDest] = useState<DestCell[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [rowStart, setRowStart] = useState<string>("A");
  const [rowEnd, setRowEnd] = useState<string>("H");
  // Debounced range applied to RPC calls; updates 250 ms after the user stops adjusting.
  const [appliedRange, setAppliedRange] = useState<MappingRange | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const { designResults, plateMappings, dedupInfo, tableSorting, yPredMap, customCandidates, echoTransferVol, janusTransferVol } = useAppStore(
    useShallow((s) => ({
      designResults: s.designResults,
      plateMappings: s.plateMappings,
      dedupInfo: s.dedupInfo,
      tableSorting: s.tableSorting,
      yPredMap: s.yPredMap,
      customCandidates: s.customCandidates,
      echoTransferVol: s.echoTransferVol,
      janusTransferVol: s.janusTransferVol,
    })),
  );

  const sortedMappings = useMemo(() => {
    const sortedMuts = getSortedMutations(designResults, tableSorting, { yPredMap, customCandidates });
    return reorderMappings(plateMappings, dedupInfo, sortedMuts);
  }, [designResults, tableSorting, yPredMap, customCandidates, plateMappings, dedupInfo]);

  const load = useCallback(async (): Promise<void> => {
    setLoading(true);
    setError(null);
    try {
      const echoParams: Record<string, unknown> = {
        mappings: sortedMappings,
        dedup_info: dedupInfo,
        transfer_vol: echoTransferVol,
      };
      const janusParams: Record<string, unknown> = {
        mappings: sortedMappings,
        dedup_info: dedupInfo,
        transfer_vol: janusTransferVol,
      };
      if (appliedRange) {
        echoParams.mapping_range = appliedRange;
        janusParams.mapping_range = appliedRange;
      }
      const [e, j] = await Promise.all([
        rpc<EchoDryRunResult>("kuro", "export_echo_mapping_dry_run", echoParams),
        rpc<JanusDryRunResult>("kuro", "export_janus_mapping_dry_run", janusParams),
      ]);
      const echoRows = e?.rows ?? [];
      const janusRows = j?.rows ?? [];
      setEcho(adaptEchoRows(echoRows));
      setEchoDest(adaptDestCellsEcho(echoRows));
      setJanus(adaptJanusRows(janusRows));
      setJanusDest(adaptDestCellsJanus(janusRows));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [sortedMappings, dedupInfo, echoTransferVol, janusTransferVol, appliedRange]);

  useEffect(() => {
    void load();
  }, [load]);

  // Debounce row range -> appliedRange. Clamp row_end >= row_start.
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      if (rowEnd < rowStart) {
        setAppliedRange({ row_start: rowStart, row_end: rowStart });
      } else if (rowStart === "A" && rowEnd === "H") {
        // Default full range -> omit param to use server default.
        setAppliedRange(null);
      } else {
        setAppliedRange({ row_start: rowStart, row_end: rowEnd });
      }
    }, 250);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [rowStart, rowEnd]);

  if (error) {
    return (
      <Card>
        <CardContent className="p-4">
          <p className="text-error">{error}</p>
          <Button size="sm" variant="outline" onClick={() => void load()} className="mt-2">
            {t("common.retry")}
          </Button>
        </CardContent>
      </Card>
    );
  }

  if (loading) {
    return (
      <Card>
        <CardContent className="p-4 text-muted-foreground">
          {t("exportPreview.loading")}
        </CardContent>
      </Card>
    );
  }

  if (echo.length === 0 && janus.rack1.length === 0 && janus.rack2.length === 0) {
    return (
      <Card>
        <CardContent className="p-4 text-muted-foreground">
          {t("exportPreview.empty")}
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("exportPreview.title")}</CardTitle>
        <CardDescription>{t("exportPreview.subtitle")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <PlateLegendsPanel />
        <div className="flex flex-wrap items-end gap-3">
          <div className="text-caption text-muted-foreground">
            {t("exportPreview.mappingRange", { defaultValue: "Mapping range" })}
          </div>
          <div className="flex items-center gap-2 min-w-0">
            <Label htmlFor="mapping-range-row-start" className="text-caption">
              {t("exportPreview.rowStart", { defaultValue: "Start" })}
            </Label>
            <div className="w-20 min-w-0">
              <Select value={rowStart} onValueChange={setRowStart}>
                <SelectTrigger id="mapping-range-row-start" aria-label={t("exportPreview.rowStart", { defaultValue: "Start" })}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {ROW_LETTERS.map((r) => (
                    <SelectItem key={r} value={r}>
                      {r}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="flex items-center gap-2 min-w-0">
            <Label htmlFor="mapping-range-row-end" className="text-caption">
              {t("exportPreview.rowEnd", { defaultValue: "End" })}
            </Label>
            <div className="w-20 min-w-0">
              <Select value={rowEnd} onValueChange={setRowEnd}>
                <SelectTrigger
                  id="mapping-range-row-end"
                  aria-label={t("exportPreview.rowEnd", { defaultValue: "End" })}
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {ROW_LETTERS.map((r) => (
                    <SelectItem key={r} value={r} disabled={r < rowStart}>
                      {r}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        </div>
        <Tabs value={view} onValueChange={(v) => setView(v as View)}>
          <TabsList>
            <TabsTrigger value="echo">{t("exportPreview.echoTab")}</TabsTrigger>
            <TabsTrigger value="janus">{t("exportPreview.janusTab")}</TabsTrigger>
          </TabsList>
          <TabsContent value="echo">
            <div className="space-y-3">
              <EchoPlateView cells={echo} />
              <DestPlateView cells={echoDest} sourceMethod="echo" />
            </div>
          </TabsContent>
          <TabsContent value="janus">
            <div className="space-y-3">
              <JanusPlateView rack1={janus.rack1} rack2={janus.rack2} />
              <DestPlateView cells={janusDest} sourceMethod="janus" />
            </div>
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}
