import { useAppStore } from "../../../store/appStore";
import { SequenceInput } from "./SequenceInput";
import { MutationInput } from "./MutationInput";

export function InputPanel() {
  const loadSampleData = useAppStore((s) => s.loadSampleData);

  return (
    <section className="space-y-3 rounded-md border border-border bg-background p-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-foreground">Input</h3>
        <button
          className="rounded-md border border-border bg-muted px-2 py-1 text-[11px] font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
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
