import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "node:path";

export default defineConfig({
  plugins: [react()],
  base: "/assets/",
  build: {
    outDir: resolve(import.meta.dirname, "../api/dashboard"),
    emptyOutDir: true,
  },
});
