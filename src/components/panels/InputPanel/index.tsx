import { useAppStore } from "../../../store/appStore";
import { SequenceInput } from "./SequenceInput";
import { MutationInput } from "./MutationInput";

export function InputPanel() {
  const loadSampleData = useAppStore((s) => s.loadSampleData);

  return (
    <section className="space-y-4 rounded-[24px] border border-slate-200 bg-gradient-to-b from-white to-amber-50/35 p-4 shadow-[0_10px_24px_rgba(15,23,42,0.05)]">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-500">Input</div>
          <h3 className="mt-1 text-lg font-semibold text-slate-950">Construct and mutation batch</h3>
        </div>
        <button
          className="rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-[11px] font-medium text-amber-800 transition-colors hover:bg-amber-100"
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
