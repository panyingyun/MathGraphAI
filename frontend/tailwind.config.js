/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: "#004ac6",
        "primary-container": "#2563eb",
        surface: "#faf8ff",
        "surface-low": "#f3f3fe",
        "surface-container": "#ededf9",
        "outline-variant": "#c3c6d7",
        ink: "#191b23",
        muted: "#5e6272",
        danger: "#ba1a1a",
      },
      fontFamily: {
        sans: [
          "Inter",
          "LXGWWenKai",
          "PingFang SC",
          "Hiragino Sans GB",
          "Microsoft YaHei",
          "sans-serif",
        ],
        display: [
          "Newsreader",
          "LXGWWenKai",
          "Georgia",
          "Times New Roman",
          "serif",
        ],
        mono: ["SF Mono", "JetBrains Mono", "Menlo", "Consolas", "monospace"],
      },
      boxShadow: {
        soft: "0 10px 30px rgba(25, 27, 35, 0.07)",
      },
    },
  },
  plugins: [],
};
