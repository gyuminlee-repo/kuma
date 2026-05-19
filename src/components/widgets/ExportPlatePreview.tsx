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
  type EchoCell,
  type JanusCell,
  type EchoDryRunRow,
  type JanusDryRunRow,
} from "@/lib/echoJanusAdapter";
import { EchoPlateView } from "./EchoPlateView";
import { JanusPlateView } from "./JanusPlateView";
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
 * Note: the design plan referenced a shadcn ToggleGroup primitive. That
 * primitive is not installed in this repo; the Tabs primitive
 * (`@/components/ui/tabs`) is semantically equivalent (single-select,
 * exclusive content, ARIA-correct) and avoids adding a new dependency.
 */
export function ExportPlatePreview() {
  const { t } = useTranslation();
  const [view, setView] = useState<View>("echo");
  const [echo, setEcho] = useState<EchoCell[]>([]);
  const [janus, setJanus] = useState<{ rack1: JanusCell[]; rack2: JanusCell[] }>({
    rack1: [],
    rack2: [],
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { designResults, plateMappings, dedupInfo, tableSorting, yPredMap, customCandidates } = useAppStore(
    useShallow((s) => ({
      designResults: s.designResults,
      plateMappings: s.plateMappings,
      dedupInfo: s.dedupInfo,
      tableSorting: s.tableSorting,
      yPredMap: s.yPredMap,
      customCandidates: s.customCandidates,
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
      const payload = { mappings: sortedMappings, dedup_info: dedupInfo };
      const [e, j] = await Promise.all([
        rpc<EchoDryRunResult>("kuro", "export_echo_mapping_dry_run", payload),
        rpc<JanusDryRunResult>("kuro", "export_janus_mapping_dry_run", payload),
      ]);
      setEcho(adaptEchoRows(e?.rows ?? []));
      setJanus(adaptJanusRows(j?.rows ?? []));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [sortedMappings, dedupInfo]);

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
            <EchoPlateView cells={echo} />
          </TabsContent>
          <TabsContent value="janus">
            <JanusPlateView rack1={janus.rack1} rack2={janus.rack2} />
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}
