import { useId, type ReactNode } from "react";

export type InspectorPanelProps = {
  title: string;
  subtitle?: string;
  children: ReactNode;
};

/**
 * InspectorPanel — right inspector column container.
 * Matches mockup CSS line 156-159: `.inspect-head` + `.inspect-scroll`.
 */
export function InspectorPanel({ title, subtitle, children }: InspectorPanelProps) {
  const headingId = useId();

  return (
    <section
      className="flex h-full flex-col overflow-hidden"
      aria-labelledby={headingId}
    >
      {/* inspect-head */}
      <div className="shrink-0 border-b border-border px-[13px] py-[13px]">
        <h3
          id={headingId}
          className="text-sm font-semibold leading-snug text-foreground"
        >
          {title}
        </h3>
        {subtitle && (
          <p className="mt-1 text-[12px] leading-snug text-muted-foreground">
            {subtitle}
          </p>
        )}
      </div>

      {/* inspect-scroll */}
      <div className="min-h-0 flex-1 overflow-y-auto p-[12px]">
        {children}
      </div>
    </section>
  );
}
