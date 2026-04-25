import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Warm Institutional palette (carried from MAS / Aegis Prime)
        ink: "#0f172a",
        paper: "#f8fafc",
        trust: "#1d4ed8",
        // Quartile semantic colors
        "q-buybuy": "#1e40af",
        "q-buy": "#0ea5e9",
        "q-sell": "#f59e0b",
        "q-sellsell": "#dc2626",
      },
    },
  },
  plugins: [],
};
export default config;
