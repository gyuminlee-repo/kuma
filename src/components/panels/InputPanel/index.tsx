import { useAppStore } from "../../../store/appStore";
import { SequenceInput } from "./SequenceInput";
import { MutationInput } from "./MutationInput";

export function InputPanel() {
  const loadSampleData = useAppStore((s) => s.loadSampleData);

  return (
    <div className="border border-gray-300 rounded p-3 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold text-gray-700 uppercase tracking-wide">
          Input
        </h3>
        <button
          className="text-[10px] text-blue-500 hover:text-blue-700 underline underline-offset-2"
          onClick={loadSampleData}
          title="Load sample GenBank + EVOLVEpro CSV to see an example result"
        >
          Try sample →
        </button>
      </div>

      <SequenceInput />
      <MutationInput />
    </div>
  );
}
