import { useEffect, useState, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
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

  const load = useCallback(async (): Promise<void> => {
    setLoading(true);
    setError(null);
    try {
      const [e, j] = await Promise.all([
        rpc<EchoDryRunResult>("kuro", "export_echo_mapping_dry_run", {}),
        rpc<JanusDryRunResult>("kuro", "export_janus_mapping_dry_run", {}),
      ]);
      setEcho(adaptEchoRows(e?.rows ?? []));
      setJanus(adaptJanusRows(j?.rows ?? []));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

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
      </CardHeader>
      <CardContent className="space-y-3">
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
