import Link from "next/link";

export default function Home() {
  return (
    <main className="mx-auto max-w-3xl px-6 py-24">
      <h1 className="text-3xl font-bold">InvestScope</h1>
      <p className="mt-3 text-neutral-400">
        재무·뉴스·거시경제를 통합한 설명 가능한 투자 스코어와, 캔들 패턴 해설을 제공합니다.
      </p>
      <Link
        href="/dashboard"
        className="mt-8 inline-block rounded-md bg-neutral-100 px-4 py-2 font-medium text-neutral-900"
      >
        대시보드 열기
      </Link>
      <p className="mt-12 text-xs text-neutral-500">
        본 서비스의 모든 정보는 참고용이며, 매매 신호나 투자 권유가 아닙니다.
      </p>
    </main>
  );
}
