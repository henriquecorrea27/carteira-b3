/// <reference types="vitest/config" />
import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  server: {
    port: 5180,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
  build: {
    rolldownOptions: {
      output: {
        // Long-lived vendor chunks, separate from app code.
        codeSplitting: {
          groups: [
            { name: "react", test: /node_modules[\\/](react|react-dom|scheduler|react-router|react-router-dom)[\\/]/ },
            { name: "ui", test: /node_modules[\\/](radix-ui|@radix-ui|cmdk|sonner|lucide-react|@tanstack)[\\/]/ },
            { name: "recharts", test: /node_modules[\\/](recharts|d3-[^\\/]+|victory-vendor|es-toolkit|immer|redux|@reduxjs|reselect|react-redux)[\\/]/ },
            { name: "tvcharts", test: /node_modules[\\/](lightweight-charts|fancy-canvas)[\\/]/ },
          ],
        },
      },
    },
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
