import type { Metadata } from "next";
import { IBM_Plex_Sans_KR, Manrope } from "next/font/google";
import "./globals.css";

// 라틴 문자·숫자는 Manrope, 한글은 IBM Plex Sans KR — 하나의 font-sans 스택에서
// 문자 종류에 따라 자동으로 갈라 쓰인다 (Manrope 는 한글 글리프가 없어 자동 폴백).
const manrope = Manrope({
  subsets: ["latin"],
  variable: "--font-manrope",
  display: "swap",
});
const plexKr = IBM_Plex_Sans_KR({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-plex-kr",
  display: "swap",
});

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
    <html lang="ko" className={`${manrope.variable} ${plexKr.variable}`}>
      <body className="bg-surface-base font-sans text-neutral-100 antialiased">
        {children}
      </body>
    </html>
  );
}
