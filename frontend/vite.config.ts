import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const API = "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/auth": API,
      "/tasks": API,
      "/admin": API,
      "/audit": API,
      "/health": API,
      "/openapi.json": API,
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
