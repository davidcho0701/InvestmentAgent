import type { ScoreMode } from "@/lib/types";

/**
 * 스냅샷 데이터는 반드시 기준 시각과 함께 표시해 실시간과 혼동되지 않게 한다 (§7).
 */
export default function ModeBadge({
  mode,
  asOf,
}: {
  mode: ScoreMode;
  asOf: string;
}) {
  if (mode === "live") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-red-500/15 px-2.5 py-1 text-xs font-medium text-red-400">
        <span className="h-1.5 w-1.5 rounded-full bg-red-500" />
        실시간
      </span>
    );
  }

  const label = new Date(asOf).toLocaleString("ko-KR", {
    dateStyle: "medium",
    timeStyle: "short",
  });

  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-500/15 px-2.5 py-1 text-xs font-medium text-amber-400">
      스냅샷 · {label} 기준
    </span>
  );
}
