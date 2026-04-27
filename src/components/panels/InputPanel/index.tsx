import { useAppStore } from "../../../store/appStore";
import { SequenceInput } from "./SequenceInput";
import { MutationInput } from "./MutationInput";

export function InputPanel() {
  const loadSampleData = useAppStore((s) => s.loadSampleData);

  return (
    <section className="space-y-3 rounded-container border bg-card p-3">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-caption font-semibold uppercase tracking-wide text-muted-foreground">Workspace</div>
          <h3 className="text-sm font-semibold text-foreground">Input</h3>
        </div>
        <button
          className="rounded-full border border-border px-2.5 py-1 text-caption font-medium text-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
          onClick={loadSampleData}
          title="Load sample GenBank + EVOLVEpro CSV to see an example result"
        >
          Try sample
        </button>
      </div>

      <SequenceInput />
      <MutationInput />
    </section>
  );
}
