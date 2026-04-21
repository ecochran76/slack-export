import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  base: "/operator/",
  plugins: [react()],
  build: {
    outDir: "dist/app",
    sourcemap: true
  }
});
