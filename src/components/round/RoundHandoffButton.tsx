/**
 * RoundHandoffButton — "Start Round N+1" 핸드오프 버튼
 *
 * - merged_table이 비어있으면 disabled
 * - 클릭 시 roundSlice.handoffNextRound 호출
 * - Phase 5에서 handoffNextRound가 KURO 연동으로 보강될 예정 (현재 stub)
 *
 * Spec: notes/specs/2026-05-04-mame-activity-integration.md §4.3
 */

import { Button } from "@/components/ui/button";
import { useRoundStore } from "@/store/round/roundSlice";
import { ArrowRight } from "lucide-react";

interface RoundHandoffButtonProps {
  round_id: string;
}

export function RoundHandoffButton({ round_id }: RoundHandoffButtonProps) {
  const round = useRoundStore((s) => s.rounds.find((r) => r.id === round_id) ?? null);
  const handoffNextRound = useRoundStore((s) => s.handoffNextRound);

  const hasMergedData = (round?.merged_table.length ?? 0) > 0;
  const disabled = !hasMergedData;
  const nextRoundN = (round?.n ?? 0) + 1;

  return (
    <Button
      type="button"
      size="sm"
      className="w-full text-xs"
      disabled={disabled}
      onClick={() => handoffNextRound(round_id)}
      aria-label={`Start Round ${nextRoundN}`}
      title={
        disabled
          ? "Merge activity data with genotype first to enable handoff"
          : undefined
      }
    >
      <ArrowRight size={12} aria-hidden="true" className="mr-1.5" />
      Start Round {nextRoundN}
    </Button>
  );
}
