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
          high: "#10b981",
          mid: "#f59e0b",
          low: "#ef4444",
        },
      },
    },
  },
  plugins: [],
};

export default config;
