import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// During local frontend development (`npm run dev`), API calls are proxied to
// the Python backend so the app behaves the same as when it is served from
// the Docker container on a single origin.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
