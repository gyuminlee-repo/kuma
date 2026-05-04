/**
 * RoundHandoffButton — "Start Round N+1" 핸드오프 버튼
 *
 * - merged_table이 비어있으면 disabled
 * - 클릭 시 roundSlice.handoffNextRound 호출
 * - KURO inputSlice.loadRoundActivity를 콜백으로 주입 (의존 그래프 분리)
 * - 탭 전환 store가 없으므로 onHandoffSuccess는 미래 확장용 콜백으로 예약
 *
 * Spec: notes/specs/2026-05-04-mame-activity-integration.md §4.3
 */

import { Button } from "@/components/ui/button";
import { useRoundStore } from "@/store/round/roundSlice";
import { useAppStore } from "@/store/appStore";
import { ArrowRight } from "lucide-react";

interface RoundHandoffButtonProps {
  round_id: string;
  /** 핸드오프 성공 시 콜백 (예: KURO 탭 전환). 탭 store 구현 전까지는 선택적. */
  onHandoffSuccess?: () => void;
}

export function RoundHandoffButton({ round_id, onHandoffSuccess }: RoundHandoffButtonProps) {
  const round = useRoundStore((s) => s.rounds.find((r) => r.id === round_id) ?? null);
  const handoffNextRound = useRoundStore((s) => s.handoffNextRound);
  const loadRoundActivity = useAppStore((s) => s.loadRoundActivity);

  const hasMergedData = (round?.merged_table.length ?? 0) > 0;
  const disabled = !hasMergedData;
  const nextRoundN = (round?.n ?? 0) + 1;

  function handleClick() {
    handoffNextRound(round_id, { loadRoundActivity, onHandoffSuccess });
  }

  return (
    <Button
      type="button"
      size="sm"
      className="w-full text-xs"
      disabled={disabled}
      onClick={handleClick}
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
