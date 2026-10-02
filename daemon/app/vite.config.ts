import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Port 1420 is the one tauri.conf.json `devUrl` points to.
export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: { port: 1420, strictPort: true },
});
