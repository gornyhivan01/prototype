import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// В dev-режиме Vite отдаёт SPA на :5173 и проксирует API/SSO на FastAPI :8000.
// Callback Keycloak приходит на :8000, оттуда мост редиректит на SPA:
// для этого backend запускается с SSO_FRONTEND_URL=http://localhost:5173.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/auth": "http://localhost:8000",
      "/users": "http://localhost:8000",
      "/health": "http://localhost:8000",
      "/docs": "http://localhost:8000",
      "/openapi.json": "http://localhost:8000",
    },
  },
});
