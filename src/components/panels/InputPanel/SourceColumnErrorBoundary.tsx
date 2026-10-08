import { Component, type ErrorInfo, type ReactNode } from "react";
import { appendCrashLog } from "../../../lib/crashLog";

interface SourceColumnErrorBoundaryProps {
  /** Localized headline shown when a render inside the boundary throws. */
  title: string;
  /** Stable identifier recorded in the crash log. */
  componentName: string;
  children: ReactNode;
}

interface SourceColumnErrorBoundaryState {
  error: Error | null;
}

/**
 * Narrow error boundary for the EVOLVEpro/Others column mapping panel.
 *
 * The shared ui/ErrorBoundary takes a static fallback node, so it can neither
 * surface the thrown message nor record it. This one does both: the error is
 * shown in place and appended to the localStorage crash log, so a render-time
 * throw inside the preview panel no longer takes down the whole KURO screen.
 */
export class SourceColumnErrorBoundary extends Component<
  SourceColumnErrorBoundaryProps,
  SourceColumnErrorBoundaryState
> {
  static getDerivedStateFromError(error: Error): SourceColumnErrorBoundaryState {
    return { error };
  }

  constructor(props: SourceColumnErrorBoundaryProps) {
    super(props);
    this.state = { error: null };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error(`[${this.props.componentName}] render error:`, error, info);
    appendCrashLog({
      component: this.props.componentName,
      message: error.message,
      stack: error.stack,
    });
  }

  render(): ReactNode {
    const { error } = this.state;
    if (error !== null) {
      return (
        <div
          role="alert"
          className="space-y-1 rounded-xl border border-destructive/40 p-2 text-xs text-destructive"
        >
          <div className="font-medium">{this.props.title}</div>
          <div className="font-mono break-all">{error.message}</div>
        </div>
      );
    }
    return this.props.children;
  }
}
