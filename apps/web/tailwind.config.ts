import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // 스코어 밴드 색상 (Part 1 게이지/팩터 바 공용)
        score: {
          high: "#2dd4bf",
          mid: "#f59e0b",
          low: "#f43f5e",
        },
        // 국내 시세 관례: 상승 = 빨강, 하락 = 파랑
        up: "#f43f5e",
        down: "#3b82f6",
        // 트레이딩 터미널 톤 배경 레이어
        surface: {
          base: "#05070a",
          DEFAULT: "#0b0e13",
          raised: "#11151c",
          overlay: "#171c25",
          border: "#1f2530",
        },
        // 브랜드 포인트 컬러 (틸)
        accent: {
          DEFAULT: "#2dd4bf",
          soft: "#0f2e2b",
          foreground: "#04120f",
        },
      },
      fontFamily: {
        sans: [
          "var(--font-manrope)",
          "var(--font-plex-kr)",
          "ui-sans-serif",
          "system-ui",
          "sans-serif",
        ],
      },
      boxShadow: {
        panel: "0 1px 0 0 rgba(255,255,255,0.03) inset, 0 8px 24px -12px rgba(0,0,0,0.6)",
      },
    },
  },
  plugins: [],
};

export default config;
