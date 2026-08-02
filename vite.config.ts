import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    // 与 README / docker-compose 一致：前端 6106 → 代理后端 6108
    port: 6106,
    proxy: {
      "/api": "http://127.0.0.1:6108",
    },
  },
  optimizeDeps: {
    include: ["plotly.js-dist-min", "katex", "react-katex", "mathjs", "lucide-react"],
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          plotly: ["plotly.js-dist-min"],
          katex: ["katex", "react-katex"],
        },
      },
    },
  },
});
