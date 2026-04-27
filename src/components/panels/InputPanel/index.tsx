import { SequenceInput } from "./SequenceInput";
import { MutationInput } from "./MutationInput";

export function InputPanel() {
  return (
    <section className="space-y-3 rounded-container border bg-card p-3">
      <div>
        <div className="text-caption font-semibold uppercase tracking-wide text-muted-foreground">Workspace</div>
        <h3 className="text-sm font-semibold text-foreground">Input</h3>
      </div>

      <SequenceInput />
      <MutationInput />
    </section>
  );
}
