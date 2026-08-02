import { fileURLToPath, URL } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
      // The taxonomy is the product's spine and it has exactly one copy.
      // ml/ reads data/taxonomy/ directly; so does the client. A second copy
      // inside web/ would drift, and the drift would be silent.
      "@taxonomy": fileURLToPath(new URL("../data/taxonomy", import.meta.url)),
    },
  },
  server: {
    port: 5173,
    fs: {
      // Reach up one level for data/taxonomy only.
      allow: [fileURLToPath(new URL(".", import.meta.url)), fileURLToPath(new URL("../data", import.meta.url))],
    },
  },
});
