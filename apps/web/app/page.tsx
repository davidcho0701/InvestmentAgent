import Link from "next/link";
import LogoMark from "@/components/shared/LogoMark";

export default function Home() {
  return (
    <main className="relative min-h-screen overflow-hidden">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-[-20%] h-[520px] bg-[radial-gradient(ellipse_at_top,_rgba(45,212,191,0.14),_transparent_60%)]"
      />

      <header className="relative mx-auto flex max-w-5xl items-center justify-between px-6 py-6">
        <div className="flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-md bg-accent/15 text-accent">
            <LogoMark className="h-4 w-4" />
          </span>
          <span className="text-sm font-semibold tracking-wide text-neutral-200">
            NewsFin Quant
          </span>
        </div>
        <Link
          href="/dashboard"
          className="rounded-md border border-surface-border px-3 py-1.5 text-xs font-medium text-neutral-300 transition hover:border-accent/40 hover:text-accent"
        >
          대시보드 →
        </Link>
      </header>

      <section className="relative mx-auto max-w-3xl px-6 pb-24 pt-16 sm:pt-24">
        <span className="inline-flex items-center gap-1.5 rounded-full border border-surface-border bg-surface px-3 py-1 text-[11px] font-medium tracking-wide text-neutral-400">
          <span className="h-1.5 w-1.5 rounded-full bg-accent" />
          재무 · 뉴스 · 거시 통합 스코어
        </span>

        <h1 className="mt-6 text-4xl font-bold leading-tight tracking-tight text-neutral-50 sm:text-5xl">
          숫자 뒤의 이유까지
          <br />
          <span className="text-accent">설명 가능한</span> 투자 스코어
        </h1>

        <p className="mt-5 max-w-xl text-base leading-7 text-neutral-400">
          DART 재무제표, 뉴스 감성, 거시지표, 애널리스트 컨센서스를 한 화면에서 종합해
          0~100점의 스코어와 근거 문장을 함께 보여줍니다. 매매 신호가 아닌, 판단을 돕는
          참고 정보입니다.
        </p>

        <div className="mt-9 flex flex-wrap items-center gap-4">
          <Link
            href="/dashboard"
            className="inline-flex items-center gap-2 rounded-md bg-accent px-5 py-2.5 text-sm font-semibold text-accent-foreground shadow-panel transition hover:brightness-110"
          >
            대시보드 열기
            <span aria-hidden>→</span>
          </Link>
          <span className="text-xs text-neutral-500">
            종목 검색 → 스냅샷 리포트 → 관심종목 등록(최대 3개) → 실시간 전환
          </span>
        </div>

        <dl className="mt-16 grid grid-cols-2 gap-6 border-t border-surface-border pt-8 sm:grid-cols-4">
          {[
            ["재무", "발생액 비율·섹터 백분위"],
            ["뉴스", "KR-FinBERT 감성 분석"],
            ["거시", "금리·환율 민감도 반영"],
            ["차트", "패턴 해설, 신호 아님"],
          ].map(([label, desc]) => (
            <div key={label}>
              <dt className="text-sm font-semibold text-neutral-200">{label}</dt>
              <dd className="mt-1 text-xs leading-5 text-neutral-500">{desc}</dd>
            </div>
          ))}
        </dl>
      </section>

      <p className="relative mx-auto max-w-3xl px-6 pb-10 text-xs text-neutral-600">
        본 서비스의 모든 정보는 참고용이며, 매매 신호나 투자 권유가 아닙니다.
      </p>
    </main>
  );
}
