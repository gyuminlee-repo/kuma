import { useEffect, useMemo, useState, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { useShallow } from "zustand/react/shallow";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
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

/**
 * ExportPlatePreview
 *
 * Container widget that fetches Echo + JANUS mapping dry-run rows from the
 * Kuro sidecar on mount, adapts them via echoJanusAdapter, and renders the
 * 384-well Echo plate or 96-well JANUS racks under a Tabs switcher. Echo
 * and JANUS are mutually exclusive views (never rendered simultaneously).
 *
 * Source-plate placement is chosen by the quadrant selector rendered beneath
 * this preview, which is the choice the 96-head Zephyr can actually stamp.
 * A row-band picker used to sit here as well; it fed ``mapping_range``,
 * which the mapper wraps modulo the band width, so every band it could
 * express other than the full plate stacked different mutants onto one well
 * (and quadrant outranked it on the backend regardless).
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
  const { designResults, plateMappings, dedupInfo, tableSorting, yPredMap, customCandidates, echoTransferVol, janusTransferVol, echoQuadrant, echoUsedQuadrants } = useAppStore(
    useShallow((s) => ({
      designResults: s.designResults,
      plateMappings: s.plateMappings,
      dedupInfo: s.dedupInfo,
      tableSorting: s.tableSorting,
      yPredMap: s.yPredMap,
      customCandidates: s.customCandidates,
      echoTransferVol: s.echoTransferVol,
      janusTransferVol: s.janusTransferVol,
      // This preview renders below the quadrant selector in ExportStepView, so
      // an operator picks a quadrant and then checks it against the plate drawn
      // here. Until the selection reached the RPC, that check was against wells
      // the exported csv would not use.
      echoQuadrant: s.echoQuadrant,
      echoUsedQuadrants: s.echoUsedQuadrants,
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
        // Echo only. quadrant outranks mapping_range on the backend, so both
        // are sent and the sidecar decides, exactly as the export does.
        quadrant: echoQuadrant,
        used_quadrants: echoUsedQuadrants,
      };
      const janusParams: Record<string, unknown> = {
        mappings: sortedMappings,
        dedup_info: dedupInfo,
        transfer_vol: janusTransferVol,
      };
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
  }, [sortedMappings, dedupInfo, echoTransferVol, janusTransferVol, echoQuadrant, echoUsedQuadrants]);

  useEffect(() => {
    void load();
  }, [load]);

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
