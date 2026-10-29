import type { Config } from "tailwindcss";

// "Signal board" palette: cool paper, ink, and three signal colours that only ever mean status.
export default {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        paper: "#E8EDF1", panel: "#F6F8FA", ink: "#14212B", muted: "#51606C", rule: "#C5CFD8",
        go: "#1B7F55", stop: "#C0392B", wait: "#A9710F", rail: "#27557F",
      },
      fontFamily: {
        sans: ["ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
        board: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
    },
  },
  plugins: [],
} satisfies Config;
