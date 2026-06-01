import { EvolveProPanel } from "@/components/evolvepro/EvolveProPanel";

/**
 * EvolveProTab: third tool tab.
 *
 * Unlike KuroTab/MameTab (which mount AppShell with workflow sidebar + subnav),
 * EVOLVEpro is a single-form module: it renders EvolveProPanel directly inside a
 * `data-tool="evolvepro"` root so the index.css theme block applies. No
 * MajorSubnav/SubStepNav is rendered.
 */
export function EvolveProTab() {
  return (
    <div data-tool="evolvepro" className="h-full overflow-hidden bg-background">
      <EvolveProPanel />
    </div>
  );
}
