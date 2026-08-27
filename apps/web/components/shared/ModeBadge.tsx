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
      <span className="inline-flex items-center gap-1.5 rounded-full border border-up/20 bg-up/10 px-2.5 py-1 text-[11px] font-medium text-up">
        <span className="relative flex h-1.5 w-1.5">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-up opacity-60" />
          <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-up" />
        </span>
        실시간
      </span>
    );
  }

  const label = new Date(asOf).toLocaleString("ko-KR", {
    dateStyle: "medium",
    timeStyle: "short",
  });

  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-400/20 bg-amber-400/10 px-2.5 py-1 text-[11px] font-medium text-amber-300">
      스냅샷 · {label} 기준
    </span>
  );
}
