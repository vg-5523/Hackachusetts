/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          950: "#eef2f6",
          900: "#ffffff",
          800: "#e7edf3",
          700: "#dbe3ec",
          600: "#c6d0dc",
        },
        line: "#d4dbe4",
        accent: {
          DEFAULT: "#0369a1",
          dim: "#0284c7",
        },
      },
      fontFamily: {
        mono: [
          "'JetBrains Mono'",
          "'SF Mono'",
          "'Cascadia Code'",
          "Consolas",
          "ui-monospace",
          "monospace",
        ],
        sans: [
          "'Inler'",
          "ui-sans-serif",
          "system-ui",
          "sans-serif",
        ],
      },
      keyframes: {
        flagIn: {
          "0%": { opacity: "0", transform: "translateY(-6px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        critScan: {
          "0%": { boxShadow: "inset 3px 0 0 #e11d48, 0 0 0 1px rgba(225,29,72,0.5)" },
          "50%": { boxShadow: "inset 3px 0 0 #e11d48, 0 0 18px 0 rgba(225,29,72,0.25)" },
          "100%": { boxShadow: "inset 3px 0 0 #e11d48, 0 0 0 1px rgba(225,29,72,0.2)" },
        },
        tick: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.35" },
      },
      },
      animation: {
        "flag-in": "flagIn 0.35s cubic-bezier(0.16,1,0.3,1)",
        "crit-scan": "critScan 0.9s ease-out 3",
        "tick": "tick 1s step-end infinite",
      },
    },
  },
  plugins: [],
};
