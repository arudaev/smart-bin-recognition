/// <reference types="vitest/config" />
import { createHash } from "node:crypto";
import { readFileSync, readdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath, URL } from "node:url";

import react from "@vitejs/plugin-react";
import type { Plugin, ResolvedConfig } from "vite";
import { defineConfig } from "vite";

/* The service worker is hand-written in public/ so that the offline policy is
   readable in one file. Two things it cannot know about itself are filled in
   here: which hashed assets this build produced, and what to call the build.

   The name matters more than it looks. `BUILD` is the cache key, so replacing
   it is what makes a deployment evict the previous one; leaving it constant
   would serve last week's JavaScript to somebody who has already installed. */
function pwa(): Plugin {
  let config: ResolvedConfig;
  let assets: string[] = [];

  return {
    name: "sbr-pwa",
    apply: "build",
    configResolved(resolved) {
      config = resolved;
    },
    generateBundle(_options, bundle) {
      assets = Object.keys(bundle).map((file) => `${config.base}${file}`.replace(/\/{2,}/g, "/"));
    },
    closeBundle() {
      const out = config.build.outDir;

      // Everything in public/icons is small, and an icon that only appears at
      // install time is exactly the request that will be made offline.
      const icons = readdirSync(join(config.publicDir, "icons")).map((f) => `/icons/${f}`);
      const precache = ["/", "/index.html", "/manifest.webmanifest", ...icons, ...assets].filter(
        (path, index, all) => all.indexOf(path) === index,
      );

      const build = createHash("sha256").update(precache.join("\n")).digest("hex").slice(0, 12);

      writeFileSync(join(out, "precache.json"), JSON.stringify(precache, null, 2));

      const source = readFileSync(join(config.publicDir, "sw.js"), "utf8");
      const stamped = source.replace(/const BUILD = "[^"]*";/, `const BUILD = "${build}";`);
      if (stamped === source) {
        this.warn("sw.js: BUILD was not stamped – caches will not be evicted between deployments");
      }
      writeFileSync(join(out, "sw.js"), stamped);
    },
  };
}

const pkg = JSON.parse(readFileSync(fileURLToPath(new URL("./package.json", import.meta.url)), "utf8")) as {
  version: string;
};

export default defineConfig({
  plugins: [react(), pwa()],
  /* Settings tells the user which build they are looking at. A bug report that
     says "it did the wrong thing" is worth a great deal more when it also says
     which deployment did it. */
  define: {
    __APP_VERSION__: JSON.stringify(pkg.version),
    __BUILD_TIME__: JSON.stringify(new Date().toISOString().slice(0, 10)),
  },
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
      // The taxonomy is the product's spine and it has exactly one copy.
      // ml/ reads data/taxonomy/ directly; so does the client. A second copy
      // inside web/ would drift, and the drift would be silent.
      "@taxonomy": fileURLToPath(new URL("../data/taxonomy", import.meta.url)),
    },
  },
  build: {
    // The reference device is a five-year-old phone on a bad connection, so the
    // budget is enforced rather than admired: the build shouts before a
    // dependency quietly doubles what has to arrive before the first answer.
    // Raw-size warnings are a blunt instrument; the budget that is actually
    // enforced is over the wire and lives in scripts/check-bundle.mjs.
    chunkSizeWarningLimit: 210,
    reportCompressedSize: true,
    rollupOptions: {
      output: {
        // React changes on a different schedule from the app – roughly never,
        // against several times a week – so it is worth its own hashed file.
        // A user who already has it downloads only what actually changed.
        manualChunks(id) {
          if (id.includes("node_modules/react") || id.includes("node_modules/scheduler")) return "react";
          return undefined;
        },
      },
    },
  },
  server: {
    port: 5173,
    fs: {
      // Reach up one level for data/taxonomy only.
      allow: [fileURLToPath(new URL(".", import.meta.url)), fileURLToPath(new URL("../data", import.meta.url))],
    },
  },
  test: {
    // Most of what is worth testing here – the resolver, the gates, the wire
    // format, the metrics – has no DOM in it by design. jsdom is opted into per
    // file with a docblock pragma rather than imposed on the whole suite.
    environment: "node",
    include: ["src/**/*.test.{ts,tsx}"],
    setupFiles: ["src/test/setup.ts"],
    coverage: {
      provider: "v8",
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/**/*.test.{ts,tsx}", "src/dev/**", "src/test/**", "src/main.tsx"],
    },
  },
});
