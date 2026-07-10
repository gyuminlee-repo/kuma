import { useCallback, useEffect, useMemo, useState } from "react";
import type { AppTab } from "@/components/layout/GlobalAppBar";
import type { KumaProject } from "@/state/projectContext";
import { GuidedTour, type GuidedTourStep } from "./GuidedTour";

export const START_GUIDED_TOUR_EVENT = "kuma:start-guided-tour";

type TourKind = "overview" | AppTab;

interface ProjectTourCoordinatorProps {
  project: Exclude<KumaProject, null>;
  activeTab: AppTab;
  onTabChange: (tab: AppTab) => void;
}

const OVERVIEW_STEPS: GuidedTourStep[] = [
  {
    target: '[data-tour="global-navigation"]',
    titleKey: "guidedTour.overviewNavigationTitle",
    bodyKey: "guidedTour.overviewNavigationBody",
  },
  {
    target: '[data-tour="project-status"]',
    titleKey: "guidedTour.overviewProjectTitle",
    bodyKey: "guidedTour.overviewProjectBody",
  },
];

const KURO_STEPS: GuidedTourStep[] = [
  {
    target: '[data-tour="kuro-workflow"]',
    titleKey: "guidedTour.kuroWorkflowTitle",
    bodyKey: "guidedTour.kuroWorkflowBody",
  },
  {
    target: '[data-tour="kuro-workspace"]',
    titleKey: "guidedTour.kuroWorkspaceTitle",
    bodyKey: "guidedTour.kuroWorkspaceBody",
  },
  {
    target: '[data-tour="kuro-inspector"]',
    titleKey: "guidedTour.kuroInspectorTitle",
    bodyKey: "guidedTour.kuroInspectorBody",
  },
];

const MAME_STEPS: GuidedTourStep[] = [
  {
    target: '[data-tour="mame-workflow"]',
    titleKey: "guidedTour.mameWorkflowTitle",
    bodyKey: "guidedTour.mameWorkflowBody",
  },
  {
    target: '[data-tour="mame-workspace"]',
    titleKey: "guidedTour.mameWorkspaceTitle",
    bodyKey: "guidedTour.mameWorkspaceBody",
  },
  {
    target: '[data-tour="mame-inspector"]',
    titleKey: "guidedTour.mameInspectorTitle",
    bodyKey: "guidedTour.mameInspectorBody",
  },
];

function tourStorageKey(project: Exclude<KumaProject, null>, kind: TourKind | "enabled"): string {
  const identity = project.project_id ?? project.path;
  return `kuma:guided-tour:${encodeURIComponent(identity)}:${kind}`;
}

export function ProjectTourCoordinator({
  project,
  activeTab,
  onTabChange,
}: ProjectTourCoordinatorProps) {
  const [tour, setTour] = useState<TourKind | null>(null);

  const steps = useMemo(() => {
    if (tour === "overview") return OVERVIEW_STEPS;
    if (tour === "kuro") return KURO_STEPS;
    if (tour === "mame") return MAME_STEPS;
    return [];
  }, [tour]);

  useEffect(() => {
    if (project.scratch) return;
    const enabledKey = tourStorageKey(project, "enabled");
    if (project.newlyCreated) localStorage.setItem(enabledKey, "1");
    if (!localStorage.getItem(enabledKey)) return;

    if (!localStorage.getItem(tourStorageKey(project, "overview"))) {
      setTour("overview");
      return;
    }
    if (!localStorage.getItem(tourStorageKey(project, activeTab))) {
      setTour(activeTab);
    }
  }, [activeTab, project]);

  useEffect(() => {
    const handleStartTour = () => setTour(activeTab);
    window.addEventListener(START_GUIDED_TOUR_EVENT, handleStartTour);
    return () => window.removeEventListener(START_GUIDED_TOUR_EVENT, handleStartTour);
  }, [activeTab]);

  useEffect(() => {
    if (tour === "kuro" && activeTab !== "kuro") onTabChange("kuro");
    if (tour === "mame" && activeTab !== "mame") onTabChange("mame");
  }, [activeTab, onTabChange, tour]);

  const handleComplete = useCallback(() => {
    if (!tour) return;
    localStorage.setItem(tourStorageKey(project, tour), "1");
    if (tour === "overview") {
      setTour("kuro");
      return;
    }
    setTour(null);
  }, [project, tour]);

  const handleSkip = useCallback(() => {
    localStorage.setItem(tourStorageKey(project, "overview"), "1");
    localStorage.setItem(tourStorageKey(project, "kuro"), "1");
    localStorage.setItem(tourStorageKey(project, "mame"), "1");
    setTour(null);
  }, [project]);

  const handleDismiss = useCallback(() => {
    setTour(null);
  }, []);

  if (!tour || steps.length === 0) return null;

  return (
    <GuidedTour
      steps={steps}
      onComplete={handleComplete}
      onSkip={handleSkip}
      onDismiss={handleDismiss}
    />
  );
}
