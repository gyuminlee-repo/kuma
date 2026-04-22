import { useAppStore } from "../../../store/appStore";
import { SequenceInput } from "./SequenceInput";
import { MutationInput } from "./MutationInput";

export function InputPanel() {
  const loadSampleData = useAppStore((s) => s.loadSampleData);

  return (
    <section className="space-y-3 rounded-[20px] border border-zinc-900/8 bg-white/90 p-3 shadow-[0_10px_24px_rgba(24,24,27,0.05)]">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-[0.22em] text-zinc-500">Workspace</div>
          <h3 className="text-sm font-semibold text-zinc-950">Input</h3>
        </div>
        <button
          className="rounded-full border border-zinc-300 bg-zinc-950 px-2.5 py-1 text-[11px] font-medium text-zinc-100 transition-colors hover:bg-zinc-800"
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
