/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: "#c15f3c",
        "primary-container": "#d4784f",
        surface: "#fcfaf8",
        "surface-low": "#f3f0ef",
        "surface-container": "#ebe6e2",
        "outline-variant": "#e7e2dd",
        ink: "#26251e",
        muted: "#504f49",
        danger: "#b5473a",
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
        soft: "0 10px 30px rgba(38, 37, 30, 0.07)",
      },
    },
  },
  plugins: [],
};
