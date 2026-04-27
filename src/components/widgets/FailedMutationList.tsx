import type { FailedMutation } from "../../types/models";

export function FailedMutationList({
  failedMutations,
  onSelect,
}: {
  failedMutations: FailedMutation[];
  onSelect: (failed: FailedMutation) => void;
}) {
  return (
    <div className="text-caption text-destructive font-mono flex flex-wrap gap-1">
      {failedMutations.map((f) => (
        <span
          key={f.mutation}
          className="bg-destructive/10 px-1.5 py-0.5 rounded cursor-pointer hover:bg-destructive/20"
          title={`#${f.rank} | ${f.reason}`}
          onClick={() => onSelect(f)}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => e.key === "Enter" && onSelect(f)}
        >
          #{f.rank} {f.mutation}
        </span>
      ))}
    </div>
  );
}
