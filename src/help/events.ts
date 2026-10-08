import { topicForStep } from "./topics";

/**
 * A menu bar asks the shell to open the help panel. The panel lives in MainShell,
 * outside the tab contents, because an inactive tab is unmounted and would take
 * a panel rendered inside it down with it (spec C1).
 */
export const OPEN_HELP_EVENT = "kuma:open-help";

export interface OpenHelpDetail {
  topic: string;
}

export function requestHelpForStep(step: string | null | undefined): void {
  window.dispatchEvent(
    new CustomEvent<OpenHelpDetail>(OPEN_HELP_EVENT, { detail: { topic: topicForStep(step) } }),
  );
}
