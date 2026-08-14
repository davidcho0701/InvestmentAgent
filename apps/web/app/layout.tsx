import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "InvestScope",
  description: "재무·뉴스·거시경제 통합 투자 스코어 + 실시간 차트 해설",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ko">
      <body className="bg-neutral-950 text-neutral-100 antialiased">
        {children}
      </body>
    </html>
  );
}
