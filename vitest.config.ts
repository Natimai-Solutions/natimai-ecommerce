import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

// Unit tests + coverage for the shared engine (@app/utils: currency / format /
// date helpers shared by the storefront and admin apps). The Quasar apps are
// covered by typecheck + lint in CI; this is the "frontend" coverage badge.
export default defineConfig({
  resolve: {
    alias: {
      "@app/ui": fileURLToPath(new URL("./shared/ui/src", import.meta.url)),
      // Les stores de la vitrine importent leurs voisins par `@/…` ; leurs
      // tests remplacent (vi.mock) les modules qui touchent le réseau.
      "@": fileURLToPath(new URL("./frontend/src", import.meta.url)),
    },
  },
  test: {
    // Le moteur partagé, plus les tests unitaires purement TS de la vitrine
    // (config légale…) : il n'existait aucun point d'entrée pour eux.
    include: [
      "shared/**/src/**/*.test.ts",
      "frontend/src/**/*.test.ts",
      "admin-frontend/src/**/*.test.ts",
    ],
    coverage: {
      provider: "v8",
      reporter: ["text", "json-summary", "json"],
      reportsDirectory: "./coverage",
      include: ["shared/utils/src/**/*.ts"],
      exclude: ["**/*.test.ts", "**/index.ts", "shared/utils/src/i18n/**"],
    },
  },
});
