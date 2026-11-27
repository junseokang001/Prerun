import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#191f28",
        sub: "#6b7684",
        line: "#e5e8eb",
        paper: "#f2f4f6",
        up: "#f04452",
        down: "#3182f6",
      },
      boxShadow: {
        card: "0 8px 28px -18px rgba(25, 31, 40, 0.35)",
      },
      fontFamily: {
        sans: ["Pretendard", "Apple SD Gothic Neo", "Noto Sans KR", "sans-serif"],
      },
    },
  },
  plugins: [],
};

export default config;
